"""Loyalty-points service backed by Valkey (corrected).

Same contract as ``service.py``; ``award`` uses the store's atomic increment.
"""

import redis


def connect(host, port):
    return redis.Redis(host=host, port=port, single_connection_client=True, socket_timeout=5)


def award(r, member, points):
    """Add ``points`` to ``member``'s balance and return the new balance."""
    return int(r.incrby(f"points:{member}", points))


def balance(r, member):
    return int(r.get(f"points:{member}") or 0)
