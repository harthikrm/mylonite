"""THREAT_MODEL.md §8 evidence for running the third-party cart without a model (SECURITY_CHECK.md).

Part 1, containment fixtures. Each runs in a container with the cart's exact flags
(``Sandbox.start_service``: same hardening, limits, user, tmpfs and network), using our own
executor image because the cart image has no shell or interpreter:
  fork_bomb      unbounded fork loop: the pids limit must hold, the store must stay responsive,
                 and the host must be able to kill it
  busy_loop      infinite loop: the CPU limit must hold and the host must be able to kill it
  memory_hog     allocates until stopped: the memory limit must OOM-kill it
  filesystem     tmpfs fills up at its size cap, the root filesystem is read-only, /tmp is noexec,
                 and the network has no egress
Part 2, inspection of a full D1 bring-up started with a canary MODEL_API_KEY in the host
environment: the canary must not appear in any container's environment or logs, and no
container may mount the Docker socket, $HOME, the repository root or .env.

Usage: sandbox_check.py
"""

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-10-28-d1-gate"))

import d1  # noqa: E402
from d1 import REPO  # noqa: E402
from mylonite.sandbox import EXECUTOR_D1_IMAGE, LOCKED_DOWN, Sandbox, docker, limits  # noqa: E402

CART_MEMORY, CART_USER = "160m", "1654:1654"
CREDENTIAL = r"API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL"
FORK_BOMB = "import os\nwhile True:\n    try:\n        os.fork()\n    except OSError:\n        pass\n"
BUSY_LOOP = "while True:\n    pass\n"
MEMORY_HOG = "chunks = []\nwhile True:\n    chunks.append(bytearray(1 << 20))\n"
FILESYSTEM = r"""
import json, os, socket, stat
out = {}
written = 0
try:
    with open("/tmp/fill", "wb") as f:
        while True:
            f.write(b"x" * (1 << 20)); f.flush(); written += 1
except OSError as exc:
    out["tmpfs_fill"] = f"stopped after {written} MiB: {exc.strerror}"
os.remove("/tmp/fill")
try:
    open("/rootfs-probe", "w")
    out["rootfs_write"] = "WRITABLE"
except OSError as exc:
    out["rootfs_write"] = f"refused: {exc.strerror}"
with open("/tmp/probe.sh", "w") as f:
    f.write("#!/bin/sh\necho ran\n")
os.chmod("/tmp/probe.sh", stat.S_IRWXU)
try:
    os.execv("/tmp/probe.sh", ["/tmp/probe.sh"])
except OSError as exc:
    out["tmp_exec"] = f"refused: {exc.strerror}"
try:
    socket.create_connection(("1.1.1.1", 443), timeout=2).close()
    out["egress_tcp"] = "REACHABLE"
except OSError as exc:
    out["egress_tcp"] = f"blocked: {type(exc).__name__}"
print(json.dumps(out))
"""


def fixture(box, name, code, detach=True):
    """A container with the cart's flags running ``code`` with our image's Python."""
    container = f"{box.name}-fx-{name}"
    args = ["run", "--name", container, "--network", box.network, *LOCKED_DOWN, *limits(CART_MEMORY),
            "--user", CART_USER, "--tmpfs", "/tmp:rw,size=32m,noexec", "--log-opt", "max-size=10m",
            "--env-file", "/dev/null", "--entrypoint", "python", EXECUTOR_D1_IMAGE, "-c", code]
    if detach:
        docker(*args[:1], "-d", *args[1:])
    else:
        return container, subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)
    return container, None


def state(container):
    fmt = "{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}"
    return docker("inspect", "--format", fmt, container).stdout.split()


def stats(container):
    out = docker("stats", "--no-stream", "--format", "{{.CPUPerc}} {{.PIDs}} {{.MemUsage}}", container)
    cpu, pids, *mem = out.stdout.split()
    return {"cpu_percent": float(cpu.rstrip("%")), "pids": int(pids), "memory": " ".join(mem)}


def ping_ms(box):
    t0 = time.monotonic()
    reply = docker("exec", box.store, "valkey-cli", "ping").stdout.strip()
    return reply, round((time.monotonic() - t0) * 1000, 1)


def kill(container):
    t0 = time.monotonic()
    subprocess.run(["docker", "kill", container], capture_output=True)
    while state(container)[0] == "running" and time.monotonic() - t0 < 30:
        time.sleep(0.2)
    seconds = round(time.monotonic() - t0, 2)
    subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    return seconds


def containment():
    box = Sandbox("mylonite-d1sec", REPO)
    box.up()
    out = {"baseline_store_ping": ping_ms(box)}
    try:
        container, _ = fixture(box, "forkbomb", FORK_BOMB)
        time.sleep(8)
        out["fork_bomb"] = {"after_8s": stats(container), "store_ping_during": ping_ms(box),
                            "kill_seconds": kill(container)}
        container, _ = fixture(box, "busyloop", BUSY_LOOP)
        time.sleep(5)
        out["busy_loop"] = {"after_5s": stats(container), "kill_seconds": kill(container)}
        container, _ = fixture(box, "memhog", MEMORY_HOG)
        t0 = time.monotonic()
        while state(container)[0] == "running" and time.monotonic() - t0 < 60:
            time.sleep(0.2)
        status, code, oom = state(container)
        out["memory_hog"] = {"status": status, "exit_code": int(code), "oom_killed": oom == "true",
                             "seconds": round(time.monotonic() - t0, 1)}
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        container, done = fixture(box, "fs", FILESYSTEM, detach=False)
        out["filesystem"] = json.loads(done.stdout) if done.returncode == 0 else {"error": done.stderr[-500:]}
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    finally:
        box.down()
    out["pass"] = {
        "fork_bomb_pids_capped": out["fork_bomb"]["after_8s"]["pids"] <= 256,
        "fork_bomb_store_responsive": out["fork_bomb"]["store_ping_during"][0] == "PONG",
        "fork_bomb_killed": out["fork_bomb"]["kill_seconds"] < 30,
        "busy_loop_cpu_capped": out["busy_loop"]["after_5s"]["cpu_percent"] <= 110,
        "busy_loop_killed": out["busy_loop"]["kill_seconds"] < 30,
        "memory_oom_killed": out["memory_hog"]["oom_killed"],
        "tmpfs_capped": "stopped after" in out["filesystem"].get("tmpfs_fill", ""),
        "rootfs_read_only": out["filesystem"].get("rootfs_write", "").startswith("refused"),
        "tmp_noexec": out["filesystem"].get("tmp_exec", "").startswith("refused"),
        "no_egress": out["filesystem"].get("egress_tcp", "").startswith("blocked"),
    }
    return out


def inspection():
    canary = f"mylonite-canary-{uuid.uuid4().hex}"
    os.environ["MODEL_API_KEY"] = canary  # this process only; the real key is never read here
    home, repo = str(Path.home()), str(REPO)
    out = {"containers": {}}
    with d1.bringup(name="mylonite-d1sec", warmup=5) as (box, session, target, info):
        names = [box.store, session.container] + box.services
        for name in names:
            data = json.loads(docker("inspect", name).stdout)[0]
            mounts = [{"type": m["Type"], "source": m.get("Source", ""), "destination": m["Destination"],
                       "rw": m["RW"]} for m in data["Mounts"]]
            logs = docker("logs", name).stdout + docker("logs", name).stderr
            host = data["HostConfig"]
            out["containers"][name] = {
                "user": data["Config"]["User"], "read_only": host["ReadonlyRootfs"],
                "cap_drop": host["CapDrop"], "cap_add": host["CapAdd"], "privileged": host["Privileged"],
                "security_opt": host["SecurityOpt"], "pids_limit": host["PidsLimit"],
                "memory": host["Memory"], "memory_swap": host["MemorySwap"], "nano_cpus": host["NanoCpus"],
                "network": host["NetworkMode"], "published_ports": host["PortBindings"],
                "tmpfs": host["Tmpfs"], "mounts": mounts,
                "env_names": sorted(e.split("=", 1)[0] for e in data["Config"]["Env"]),
                "canary_in_env": any(canary in e for e in data["Config"]["Env"]),
                "canary_in_logs": canary in logs}
        out["egress_probe"] = session.ready.get("egress_probe")
        out["network_internal"] = json.loads(docker("network", "inspect", box.network).stdout)[0]["Internal"]
    every = out["containers"].values()
    sources = [m["source"] for c in every for m in c["mounts"]]
    out["pass"] = {
        "canary_absent": not any(c["canary_in_env"] or c["canary_in_logs"] for c in every),
        # credential-like names only: VALKEY_* is the store's, and the Python base image's GPG_KEY
        # is the public fingerprint of its release-signing key
        "no_credential_variables": not any(re.search(CREDENTIAL, n) for c in every for n in c["env_names"]),
        "no_docker_socket": not any("docker.sock" in s for s in sources),
        "no_home_repo_or_env_mount": not any(s in (home, repo) or s.endswith(".env") for s in sources),
        "mounts_read_only": all(not m["rw"] for c in every for m in c["mounts"] if m["type"] == "bind"),
        "non_root": all(c["user"] not in ("", "0", "root") and not c["user"].startswith("0:") for c in every),
        "read_only_rootfs": all(c["read_only"] for c in every),
        "caps_dropped": all(c["cap_drop"] == ["ALL"] and not c["cap_add"] for c in every),
        "unprivileged": not any(c["privileged"] for c in every),
        "no_new_privileges": all("no-new-privileges" in (c["security_opt"] or []) for c in every),
        "limits_set": all(c["pids_limit"] == 256 and c["memory"] > 0 and c["memory_swap"] == c["memory"]
                          and c["nano_cpus"] == 10**9 for c in every),
        "no_published_ports": not any(c["published_ports"] for c in every),
        "internal_network": out["network_internal"],
        "egress_blocked": all(v.startswith("blocked") for v in (out["egress_probe"] or {"x": "missing"}).values()),
    }
    return out


def main():
    report = {"commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                                       text=True).stdout.strip(),
              "dirty": bool(subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                                           capture_output=True, text=True).stdout.strip()),
              "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    report["containment"] = containment()
    report["inspection"] = inspection()
    report["all_pass"] = all(report["containment"]["pass"].values()) and all(report["inspection"]["pass"].values())
    out = REPO / "runs" / f"d1sec-{time.strftime('%Y%m%d-%H%M%S')}.json"  # copied to results/ after the run
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({"containment": report["containment"]["pass"], "inspection": report["inspection"]["pass"],
                      "all_pass": report["all_pass"]}, indent=1))
    print(out)


if __name__ == "__main__":
    main()
