"""Product inventory backed by Valkey (corrected).

Same contract and operations as ``service.py``. ``purchase`` checks and takes stock in one
server-side script, so no other command can run between the check and the decrement.
"""

from .service import Conflict, InsufficientStock, NotFound, Unavailable  # noqa: F401
from .service import connect, create, publish, restock, retire, status, stock, unpublish  # noqa: F401

_PURCHASE = """
local current = redis.call('HGET', KEYS[1], 'status')
if not current then return -3 end
if current ~= 'live' then return -1 end
local available = tonumber(redis.call('GET', KEYS[2]) or '0')
if available < tonumber(ARGV[1]) then return -2 end
redis.call('DECRBY', KEYS[2], ARGV[1])
redis.call('INCRBY', KEYS[3], ARGV[1])
return 1
"""


def purchase(r, sku, qty):
    result = r.eval(_PURCHASE, 3, f"product:{sku}", f"stock:{sku}", f"sold:{sku}", qty)
    if result == -3:
        raise NotFound(sku)
    if result == -1:
        raise Unavailable(sku)
    if result == -2:
        raise InsufficientStock(sku)
    return qty

