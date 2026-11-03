"""Compare a pilot replay with the original pilot, trial by trial. Standard library only.

  python3 experiments/2026-11-03-pilot-replay/compare.py <original trials.json> <replay trials.json>

Prints, for each compared field, the trials whose values differ, and exits 1 if any do. Timing
fields (method, model, execution and overhead seconds) are not compared: real time is not
seeded. The replay's model latency is the recorded one, so model seconds and dollars are
reported for information.
"""

import json
import sys

FIELDS = ("status", "e1_executions", "executions", "witness", "counters", "model_calls",
          "model_usd", "tokens", "unverified_violations")


def main():
    original, replay = (json.loads(open(path).read()) for path in sys.argv[1:3])
    key = lambda t: (t["target"], t["method"], t["seed"])
    a, b = {key(t): t for t in original}, {key(t): t for t in replay}
    report = {"trials": [len(a), len(b)], "same_trials": a.keys() == b.keys(),
              "differ": {f: [list(k) for k in sorted(a) if a[k].get(f) != b.get(k, {}).get(f)]
                         for f in FIELDS}}
    print(json.dumps(report, indent=1))
    sys.exit(0 if report["same_trials"] and not any(report["differ"].values()) else 1)


if __name__ == "__main__":
    main()
