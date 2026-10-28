"""Scheduling policies, exhaustive enumeration, trace hashing and the soundness check.

A decision is a label: ``admit:<op>`` (issue that operation's request) or ``exec:<op>`` (run the
head command that operation has waiting at the proxy). Policies only ever pick among the labels
the controller offers, so they cannot express an unreachable schedule (ARCHITECTURE.md §5.2).
"""

import hashlib
import json
import random


class Divergence(Exception):
    """A replay or prefix asked for a choice that the execution did not offer."""


class PrefixPolicy:
    """Follow a list of choice indices, then always take the first choice."""

    def __init__(self, prefix):
        self.prefix = list(prefix)

    def choose(self, step, choices, held):
        if step < len(self.prefix):
            if self.prefix[step] >= len(choices):
                raise Divergence(f"step {step}: index {self.prefix[step]} of {choices}")
            return choices[self.prefix[step]]
        return choices[0]


class RandomPolicy:
    def __init__(self, seed):
        self.rng = random.Random(seed)

    def choose(self, step, choices, held):
        return self.rng.choice(choices)


class ReplayPolicy:
    def __init__(self, labels):
        self.labels = list(labels)

    def choose(self, step, choices, held):
        if step >= len(self.labels) or self.labels[step] not in choices:
            want = self.labels[step] if step < len(self.labels) else None
            raise Divergence(f"step {step}: wanted {want}, offered {choices}")
        return self.labels[step]


class HintPolicy:
    """Follow a model hint [{op_index, command}]: the listed commands run in the listed order.
    To reach a step, the operation is admitted if needed and its earlier commands run first.
    A step whose operation finishes without issuing the command is skipped. Then first choice."""

    def __init__(self, hint):
        self.hint = list(hint)
        self.followed = self.skipped = self.advanced = 0

    def choose(self, step, choices, held):
        while self.hint:
            op, command = self.hint[0]["op_index"], self.hint[0]["command"]
            if f"exec:{op}" in choices:
                if held.get(op) == command:
                    self.hint.pop(0)
                    self.followed += 1
                else:
                    self.advanced += 1  # an earlier command of the same operation
                return f"exec:{op}"
            if f"admit:{op}" in choices:
                return f"admit:{op}"
            self.hint.pop(0)
            self.skipped += 1
        return choices[0]

    def stats(self):
        return {"hint_followed": self.followed, "hint_skipped": self.skipped + len(self.hint),
                "hint_advanced": self.advanced}


def next_prefix(steps):
    """Depth-first successor of an executed decision sequence, or None when exhausted.

    ``steps`` is the list of (chosen index, number of choices) recorded by an execution.
    """
    for i in range(len(steps) - 1, -1, -1):
        index, count = steps[i]
        if index + 1 < count:
            return [s[0] for s in steps[:i]] + [index + 1]
    return None


def trace_hash(decisions, events):
    """Hash of everything that must repeat on replay; timestamps and sequence numbers excluded."""
    body = {
        "decisions": decisions,
        "execs": [[e["op"], e["cmd"], e["key"], e["args"], e["reply"]]
                  for e in events if e["event"] == "exec"],
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def soundness_problems(events):
    """Check a round's trace against the ordering rules (ARCHITECTURE.md §5.2)."""
    problems = []
    arrivals = {}
    for e in events:
        if e["event"] == "arrive":
            arrivals.setdefault(e["conn"], []).append(e["seq"])
        elif e["event"] == "exec":
            queue = arrivals.get(e["conn"], [])
            if not queue:
                problems.append(f"exec without arrival on conn {e['conn']} at seq {e['seq']}")
            else:
                queue.pop(0)  # per-connection FIFO: the oldest arrival is the one executed
        elif e["event"] == "unattributed":
            problems.append(f"unattributed {e['cmd']} on conn {e['conn']}")
        elif e["event"] == "ungated":
            problems.append(f"unscheduled {e['cmd']} on conn {e['conn']}")
    return problems
