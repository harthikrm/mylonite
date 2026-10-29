"""Runs inside the sandbox for gate.py's ``natural`` stage: no proxy and no scheduler. The cart
is connected to Valkey directly, as in the demo, and two AddItem(u1, P, 1) calls are released
together from two threads on one HTTP/2 channel. Counts how often a quantity is lost.

Usage: natural.py <cart host:port> <valkey host:port> <rounds>
"""

import collections
import json
import statistics
import sys
import threading
import time

import redis

from mylonite.adapters import otel_cart

PRODUCT = "OLJCESPC7Z"


def main():
    cart, store, rounds = sys.argv[1], sys.argv[2], int(sys.argv[3])
    admin = redis.Redis(host=store.split(":")[0], port=int(store.split(":")[1]))
    svc = otel_cart.bind({"host": cart.split(":")[0], "port": int(cart.split(":")[1])})
    client = svc.connect(None, None)
    deadline = time.monotonic() + 60
    while True:  # ready, then warm up the same paths serially
        try:
            svc.GetCart(client, "u1")
            break
        except otel_cart.Unreachable:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)
    for _ in range(50):
        svc.AddItem(client, "u1", PRODUCT, 1)
        svc.GetCart(client, "u1")
    finals, outcomes, ms = collections.Counter(), collections.Counter(), []
    lost = 0
    for _ in range(rounds):
        admin.flushall()
        barrier, results = threading.Barrier(2), [None, None]

        def go(k):
            barrier.wait()
            try:
                svc.AddItem(client, "u1", PRODUCT, 1)
                results[k] = "ok"
            except Exception as exc:
                results[k] = type(exc).__name__

        started = time.perf_counter()
        threads = [threading.Thread(target=go, args=(k,)) for k in (0, 1)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ms.append((time.perf_counter() - started) * 1000)
        final = svc.GetCart(client, "u1").get(PRODUCT, 0)
        finals[final] += 1
        outcomes[",".join(sorted(results))] += 1
        lost += results == ["ok", "ok"] and final < 2
    print(json.dumps({"rounds": rounds, "lost_updates": lost, "lost_rate": round(lost / rounds, 4),
                      "final_quantity": dict(finals), "outcomes": dict(outcomes),
                      "round_ms_median": round(statistics.median(ms), 3)}))


if __name__ == "__main__":
    main()
