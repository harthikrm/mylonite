"""Adapter for D1, the OTel Demo cart (oteldemo.CartService at tag 3.1.0).

Hand-written per THREAT_MODEL.md T2: the catalog's three operations map to three gRPC methods,
and nothing else can be called. The service runs in its own container and reaches Valkey through
the proxy; this adapter is only its gRPC client. Messages are encoded here (field numbers from
pb/demo.proto at 3.1.0), so no generated code from the target is needed:

  CartItem {1: product_id string, 2: quantity int32}   AddItemRequest {1: user_id, 2: CartItem}
  GetCartRequest / EmptyCartRequest {1: user_id}        Cart {1: user_id, 2: repeated CartItem}

Errors come back as exceptions named after the gRPC status (``FailedPrecondition``, ...). A
transport failure (the cart is down or hung) raises ``Unreachable``, which the executor counts
as a harness failure, never as data for the oracle.
"""

import grpc

DEADLINE_S = 30  # longer than any round timeout: the scheduler, not the client, decides when to give up


class Unreachable(ConnectionError):
    pass


_STATUS = {}


def _status_error(code):
    name = "".join(part.capitalize() for part in code.name.split("_"))
    return _STATUS.setdefault(name, type(name, (Exception,), {}))


def _varint(n):
    n &= (1 << 64) - 1
    out = bytearray()
    while True:
        byte, n = n & 0x7F, n >> 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _field(number, wire, payload):
    tag = _varint(number << 3 | wire)
    return tag + (_varint(payload) if wire == 0 else _varint(len(payload)) + payload)


def _fields(data):
    i = 0
    while i < len(data):
        key, i = _read_varint(data, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _read_varint(data, i)
        elif wire == 2:
            size, i = _read_varint(data, i)
            value, i = data[i:i + size], i + size
        elif wire == 1:
            value, i = data[i:i + 8], i + 8
        elif wire == 5:
            value, i = data[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield number, value


def _read_varint(data, i):
    shift = result = 0
    while True:
        byte = data[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, i
        shift += 7


def _int32(value):
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def encode_user(user_id):
    return _field(1, 2, user_id.encode())


def encode_add(user_id, product_id, quantity):
    item = _field(1, 2, product_id.encode()) + _field(2, 0, quantity)
    return encode_user(user_id) + _field(2, 2, item)


def decode_cart(data):
    """Cart -> {product_id: quantity}. Duplicate product entries are summed, never hidden."""
    items = {}
    for number, value in _fields(data):
        if number == 2:
            product, quantity = "", 0
            for n, v in _fields(value):
                if n == 1:
                    product = v.decode()
                elif n == 2:
                    quantity = _int32(v)
            items[product] = items.get(product, 0) + quantity
    return items


class Client:
    """One shared HTTP/2 channel per executor, as the demo's own callers use; ``close`` is a no-op."""

    def __init__(self, channel):
        self.channel = channel

    def call(self, method, body):
        rpc = self.channel.unary_unary(f"/oteldemo.CartService/{method}")
        try:
            return rpc(body, timeout=DEADLINE_S)
        except grpc.RpcError as exc:
            if exc.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                raise Unreachable(f"{method}: {exc.code().name}") from None
            raise _status_error(exc.code())(f"{method}: {exc.code().name}") from None

    def close(self):
        pass


class Service:
    """The executor's view of a service: ``connect`` plus one function per catalog operation."""

    def __init__(self, address):
        self.client = Client(grpc.insecure_channel(address))

    def connect(self, host, port):  # the cart owns its store connection; host and port are unused
        return self.client

    @staticmethod
    def AddItem(client, user_id, product_id, quantity):
        client.call("AddItem", encode_add(user_id, product_id, quantity))

    @staticmethod
    def GetCart(client, user_id):
        return decode_cart(client.call("GetCart", encode_user(user_id)))

    @staticmethod
    def EmptyCart(client, user_id):
        client.call("EmptyCart", encode_user(user_id))


def bind(service):
    return Service(f"{service['host']}:{service['port']}")
