"""Bring up D1 in the sandbox: Valkey, the executor (with the proxy) and both cart builds.

The carts are started after the executor, because they connect to the proxy at startup and
exit if they cannot. Each cart is ready when a GetCart through the proxy succeeds; those
readiness calls also warm up the .NET JIT, as any long-running deployment would be.
"""

import contextlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from mylonite.sandbox import EXECUTOR_D1_IMAGE, Sandbox, docker  # noqa: E402

TARGET = REPO / "targets/d1-otel-cart/target.json"
READY = {"setup": [{"op": "GetCart", "args": {"user_id": "u1"}}], "concurrent": []}


def load_target(box):
    target = json.loads(TARGET.read_text())
    for service in target["services"].values():
        service["host"] = f"{box.name}-{service['container']}"
    return target


def wait_ready(session, variant, timeout_s=60):
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        try:  # until the cart listens, the executor reports its observation as an error
            out, _ = session.request({"op": "execute", "variant": variant, "workload": READY,
                                      "policy": {"kind": "prefix", "prefix": []}})
        except RuntimeError as exc:
            if "Unreachable" not in str(exc):
                raise
        else:
            if out["harness_error"] is None and out["setup_outcomes"] == ["ok"]:
                return round(time.monotonic() - started, 2)
        time.sleep(0.5)
    raise RuntimeError(f"{variant} cart not ready after {timeout_s}s")


@contextlib.contextmanager
def bringup(name="mylonite-d1", delta_q_ms=300, round_timeout_s=10, warmup=50):
    box = Sandbox(name, REPO, EXECUTOR_D1_IMAGE)
    box.up()
    target = load_target(box)
    try:
        with box.session(target, delta_q_ms=delta_q_ms, round_timeout_s=round_timeout_s) as session:
            runtime = target["service_runtime"]
            env = dict(runtime["env"], VALKEY_ADDR=f"{session.container}:6380")
            started = {}
            for variant, service in target["services"].items():
                t0 = time.monotonic()
                box.start_service(service["container"], service["image"], env, runtime["memory"],
                                  runtime["user"])
                started[variant] = {"ready_s": wait_ready(session, variant),
                                    "start_to_ready_s": round(time.monotonic() - t0, 2)}
                for _ in range(warmup):
                    session.request({"op": "execute", "variant": variant, "workload": READY,
                                     "policy": {"kind": "prefix", "prefix": []}})
            info = {"ready": session.ready, "services": started, "policy": box.inspect_policy(),
                    "images": box.image_ids(),
                    "service_images": {v: docker("image", "inspect", "--format", "{{.Id}}",
                                                 s["image"]).stdout.strip()
                                       for v, s in target["services"].items()}}
            yield box, session, target, info
    finally:
        box.down()


def cart_logs(box, variant, target, tail=40):
    container = f"{box.name}-{target['services'][variant]['container']}"
    done = docker("logs", "--tail", str(tail), container)
    return (done.stdout + done.stderr).splitlines()
