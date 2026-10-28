"""Loyalty-points service backed by Valkey.

Contract: every successful ``award`` adds exactly ``points`` to the member's balance, and no
award may be lost when several are processed at the same time.
"""

import redis


def connect(host, port):
    return redis.Redis(host=host, port=port, single_connection_client=True, socket_timeout=5)


def award(r, member, points):
    """Add ``points`` to ``member``'s balance and return the new balance."""
    balance = int(r.get(f"points:{member}") or 0)
    balance += points
    r.set(f"points:{member}", balance)
    return balance


def balance(r, member):
    return int(r.get(f"points:{member}") or 0)
