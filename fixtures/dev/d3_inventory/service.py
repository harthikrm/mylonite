"""Product inventory backed by Valkey.

Contract: a product's stock, as returned by ``stock``, is never negative.
"""

import redis


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Unavailable(Exception):
    pass


class InsufficientStock(Exception):
    pass


def connect(host, port):
    return redis.Redis(host=host, port=port, single_connection_client=True, socket_timeout=5,
                       decode_responses=True)


def _status(r, sku):
    current = r.hget(f"product:{sku}", "status")
    if current is None:
        raise NotFound(sku)
    return current


def create(r, sku):
    if not r.hsetnx(f"product:{sku}", "status", "draft"):
        raise Conflict(sku)


def restock(r, sku, qty):
    if _status(r, sku) == "retired":
        raise Unavailable(sku)
    return int(r.incrby(f"stock:{sku}", qty))


def publish(r, sku):
    if _status(r, sku) != "draft":
        raise Conflict(sku)
    if int(r.get(f"stock:{sku}") or 0) <= 0:
        raise InsufficientStock(sku)
    r.hset(f"product:{sku}", "status", "live")


def unpublish(r, sku):
    if _status(r, sku) != "live":
        raise Conflict(sku)
    r.hset(f"product:{sku}", "status", "draft")


def retire(r, sku):
    if _status(r, sku) == "live":
        raise Conflict(sku)
    r.hset(f"product:{sku}", "status", "retired")


def purchase(r, sku, qty):
    if _status(r, sku) != "live":
        raise Unavailable(sku)
    if int(r.get(f"stock:{sku}") or 0) < qty:
        raise InsufficientStock(sku)
    r.decrby(f"stock:{sku}", qty)
    r.incrby(f"sold:{sku}", qty)
    return qty


def stock(r, sku):
    return int(r.get(f"stock:{sku}") or 0)


def status(r, sku):
    return r.hget(f"product:{sku}", "status")
