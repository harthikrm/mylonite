"""Framing-only RESP2/RESP3 parsing.

The proxy must forward bytes unchanged (ARCHITECTURE.md §5.2 rule 1), so this module only finds
frame boundaries and splits client command arrays into their arguments. It never re-encodes.
RESP3 is supported because some clients (redis-py 8) negotiate it with HELLO 3 and do not fall
back to RESP2 when refused.
"""

SIMPLE = frozenset(b"+-:_,#(")   # one line
BLOB = frozenset(b"$=!")         # length-prefixed payload
AGGREGATE = frozenset(b"*~>")    # n frames
PAIRED = frozenset(b"%|")        # 2n frames (map, attribute)

GATED = frozenset({
    "GET", "SET", "SETNX", "SETEX", "PSETEX", "GETSET", "GETDEL", "MGET", "MSET", "MSETNX",
    "INCR", "INCRBY", "INCRBYFLOAT", "DECR", "DECRBY", "APPEND", "DEL", "UNLINK", "EXISTS",
    "EXPIRE", "PEXPIRE", "EXPIREAT", "PEXPIREAT", "PERSIST", "TTL", "PTTL",
    "HGET", "HSET", "HSETNX", "HMSET", "HMGET", "HDEL", "HINCRBY", "HINCRBYFLOAT", "HGETALL",
    "HEXISTS", "HKEYS", "HVALS", "HLEN",
    "LPUSH", "RPUSH", "LPOP", "RPOP", "LRANGE", "LLEN", "LREM", "LSET",
    "SADD", "SREM", "SMEMBERS", "SISMEMBER", "SCARD", "SPOP",
    "ZADD", "ZREM", "ZINCRBY", "ZSCORE", "ZRANGE", "ZCARD",
})
# Blocks are scheduled as one unit on their connection (ARCHITECTURE.md §5.1).
BLOCK_OPENERS = frozenset({"MULTI", "WATCH"})
BLOCK_CLOSERS = frozenset({"EXEC", "DISCARD", "UNWATCH"})
SCRIPTS = frozenset({"EVAL", "EVALSHA", "EVAL_RO", "EVALSHA_RO", "FCALL", "FCALL_RO"})
PUBSUB = frozenset({"SUBSCRIBE", "PSUBSCRIBE", "SSUBSCRIBE"})


class Incomplete(Exception):
    """The buffer ends before the frame does."""


class ProtocolError(Exception):
    """Bytes that are not RESP2."""


def frame_end(buf, pos=0):
    """Return the index just past the RESP frame that starts at ``pos``.

    An attribute frame (``|``) is metadata attached to the frame that follows it, so it is
    framed together with that frame.
    """
    if pos >= len(buf):
        raise Incomplete
    nl = buf.find(b"\r\n", pos)
    if nl < 0:
        raise Incomplete
    kind = buf[pos]
    if kind in SIMPLE:
        return nl + 2
    if kind in BLOB:
        length = int(buf[pos + 1:nl])
        if length < 0:
            return nl + 2
        end = nl + 2 + length + 2
        if len(buf) < end:
            raise Incomplete
        return end
    if kind in AGGREGATE or kind in PAIRED:
        count = int(buf[pos + 1:nl])
        cursor = nl + 2
        for _ in range(max(count, 0) * (2 if kind in PAIRED else 1)):
            cursor = frame_end(buf, cursor)
        return frame_end(buf, cursor) if kind == ord("|") else cursor
    if chr(kind).isalpha():  # inline command, client to server only
        return nl + 2
    raise ProtocolError(f"unexpected RESP type byte {chr(kind)!r}")


def is_push(frame):
    """Out-of-band RESP3 push (client tracking, pub/sub); not a reply to any command."""
    return frame[:1] == b">"


def command_parts(frame):
    """Split one client command frame into its byte-string arguments."""
    if frame[:1] != b"*":
        return frame.strip().split()
    header_end = frame.index(b"\r\n")
    count = int(frame[1:header_end])
    parts, cursor = [], header_end + 2
    for _ in range(count):
        nl = frame.index(b"\r\n", cursor)
        length = int(frame[cursor + 1:nl])
        start = nl + 2
        parts.append(frame[start:start + length])
        cursor = start + length + 2
    return parts


def command_name(parts):
    return parts[0].decode("ascii", "replace").upper() if parts else ""
