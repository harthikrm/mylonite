"""Host-side sandbox launcher (THREAT_MODEL.md §6, ARCHITECTURE.md §9).

The policy is fixed here, in code: nothing a model emits can change images, mounts, flags,
networks or limits. The executor talks to the host only through stdin and stdout.
"""

import collections
import json
import queue
import subprocess
import threading
import time
import uuid
from pathlib import Path

VALKEY_IMAGE = ("ghcr.io/valkey-io/valkey@sha256:"
                "107b203169a20ef7c87548c157f4e4a833dbbbd20fefd3a26740b7f98ac80216")  # 9.0.4-alpine3.23
EXECUTOR_IMAGE = "mylonite-exec:dev"
EXECUTOR_D1_IMAGE = "mylonite-exec-d1:dev"  # the same plus a gRPC client (docker/executor-d1.Dockerfile)
MAX_RESULT_BYTES = 64 * 1024 * 1024

LOCKED_DOWN = ["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--pids-limit", "256", "--cpus", "1"]


def limits(memory):
    return ["--memory", memory, "--memory-swap", memory]


HARDENED = LOCKED_DOWN + limits("512m")


def docker(*args, stdin=None, timeout=300):
    done = subprocess.run(["docker", *args], input=stdin, capture_output=True, text=True,
                          timeout=timeout)
    if done.returncode != 0:
        raise RuntimeError(f"docker {args[0]} exited {done.returncode}: {done.stderr[-3000:]}")
    return done


class Sandbox:
    def __init__(self, name, repo_root, executor_image=EXECUTOR_IMAGE):
        self.name = name
        self.network = f"{name}-net"
        self.store = f"{name}-valkey"
        self.repo = Path(repo_root).resolve()
        self.executor_image = executor_image
        self.services = []

    def build_executor_image(self):
        dockerfile = {EXECUTOR_IMAGE: "executor.Dockerfile", EXECUTOR_D1_IMAGE: "executor-d1.Dockerfile"}
        docker("build", "-q", "-t", self.executor_image, "-f",
               str(self.repo / "docker" / dockerfile[self.executor_image]), str(self.repo / "docker"),
               timeout=900)

    def up(self):
        self.down()
        docker("network", "create", "--internal", self.network)
        docker("run", "-d", "--name", self.store, "--network", self.network, *HARDENED,
               "--user", "999:1000", "--tmpfs", "/data:rw,size=64m",
               VALKEY_IMAGE, "valkey-server", "--save", "", "--appendonly", "no",
               "--protected-mode", "no")

    def start_service(self, name, image, env, memory, user):
        """A target service container (for example the D1 cart) on the internal network, with
        the same hardening as every other container: env is an explicit allow-list, nothing
        from the host is mounted, logs are size-capped, and there is no published port."""
        container = f"{self.name}-{name}"
        env_flags = [flag for key, value in sorted(env.items()) for flag in ("-e", f"{key}={value}")]
        docker("run", "-d", "--name", container, "--network", self.network, *LOCKED_DOWN,
               *limits(memory), "--user", user, "--tmpfs", "/tmp:rw,size=32m,noexec",
               "--log-opt", "max-size=10m", "--env-file", "/dev/null", *env_flags, image)
        self.services.append(container)
        return container

    def down(self):
        for container in self.services + [self.store]:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        self.services = []
        subprocess.run(["docker", "network", "rm", self.network], capture_output=True)

    def run_executor(self, request, timeout=1800):
        """Run one executor container on the internal network; JSON in on stdin, JSON out on stdout."""
        container = f"{self.name}-exec-{uuid.uuid4().hex[:8]}"
        request = dict(request, store=[self.store, 6379])
        cmd = ["run", "--rm", "-i", "--name", container, "--network", self.network, *HARDENED,
               "--tmpfs", "/tmp:rw,size=16m,noexec", "--user", "65534:65534",
               "-v", f"{self.repo / 'src'}:/app/src:ro",
               "-v", f"{self.repo / 'fixtures'}:/app/fixtures:ro",
               self.executor_image]
        try:
            out = docker(*cmd, stdin=json.dumps(request), timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", container], capture_output=True)
            raise
        if len(out.stdout) > MAX_RESULT_BYTES:
            raise ValueError("executor output exceeds the size cap")
        return json.loads(out.stdout)

    def executor_command(self, container):
        return ["docker", "run", "--rm", "-i", "--name", container, "--network", self.network,
                *HARDENED, "--tmpfs", "/tmp:rw,size=16m,noexec", "--user", "65534:65534",
                "-v", f"{self.repo / 'src'}:/app/src:ro",
                "-v", f"{self.repo / 'fixtures'}:/app/fixtures:ro", self.executor_image]

    def session(self, target, delta_q_ms=300, round_timeout_s=10):
        return ExecutorSession(self, target, delta_q_ms, round_timeout_s)

    def image_ids(self):
        """Provenance for run manifests: the exact images used."""
        executor = docker("image", "inspect", "--format", "{{.Id}}", self.executor_image).stdout.strip()
        return {"executor": executor, "valkey": VALKEY_IMAGE}

    def inspect_policy(self):
        """Evidence for the security checklist: the flags Docker actually applied."""
        fmt = ("{{.Name}} net={{.HostConfig.NetworkMode}} ro={{.HostConfig.ReadonlyRootfs}} "
               "user={{.Config.User}} capdrop={{.HostConfig.CapDrop}} pids={{.HostConfig.PidsLimit}} "
               "mem={{.HostConfig.Memory}} mounts={{len .Mounts}} privileged={{.HostConfig.Privileged}}")
        return docker("inspect", "--format", fmt, self.store, *self.services).stdout.strip()


class ExecutorSession:
    """One long-lived executor container on the internal network, speaking JSON lines: one
    request in, one response out. Same hardening and mounts as ``run_executor``."""

    def __init__(self, box, target, delta_q_ms, round_timeout_s, request_timeout_s=300):
        self.box, self.request_timeout = box, request_timeout_s
        self.settings = {"target": target, "store": [box.store, 6379],
                         "delta_q_ms": delta_q_ms, "round_timeout_s": round_timeout_s}
        self.container = f"{box.name}-exec-{uuid.uuid4().hex[:8]}"
        self.lines, self.stderr = queue.Queue(), collections.deque(maxlen=200)
        self.proc, self.ready, self.broken = None, None, False

    def __enter__(self):
        self.proc = subprocess.Popen(self.box.executor_command(self.container) + ["--serve"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self._pump, args=(self.proc.stdout, self.lines.put, True),
                         daemon=True).start()
        threading.Thread(target=self._pump, args=(self.proc.stderr, self.stderr.append, False),
                         daemon=True).start()
        self.ready = self._send(self.settings)
        return self

    def __exit__(self, *exc):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            subprocess.run(["docker", "kill", self.container], capture_output=True)
            self.proc.kill()

    @staticmethod
    def _pump(stream, sink, mark_eof):
        for line in stream:
            sink(line)
        if mark_eof:
            sink(None)  # the executor exited: fail the pending request now, not at the timeout

    def _send(self, obj):
        if self.broken:  # after a timeout, responses could be off by one: never reuse
            raise RuntimeError("executor session is broken; start a new one")
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()
        try:
            line = self.lines.get(timeout=self.request_timeout)
        except queue.Empty:
            self.broken = True
            raise RuntimeError(f"executor timed out; stderr: {''.join(self.stderr)[-2000:]}")
        if line is None:
            self.broken = True
            raise RuntimeError(f"executor exited; stderr: {''.join(self.stderr)[-2000:]}")
        if len(line) > MAX_RESULT_BYTES:
            raise ValueError("executor response exceeds the size cap")
        out = json.loads(line)
        if "error" in out:
            raise RuntimeError(f"executor error: {out['error']}")
        return out

    def request(self, obj):
        """Returns (response, round-trip seconds)."""
        started = time.monotonic()
        out = self._send(obj)
        return out, time.monotonic() - started
