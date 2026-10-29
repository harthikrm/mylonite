"""Delay-only RESP2 proxy and the shared scheduling state (ARCHITECTURE.md §5).

One thread per client connection, each with its own upstream connection. A connection's
commands are handled strictly in arrival order, so per-connection order can never be broken;
the scheduler can only decide *when* a connection's head command runs, and which connection
goes next. A single lock keeps at most one gated command (or block) in flight to the store.

A multiplexed client (several operations on one connection, as StackExchange.Redis does) gets a
second thread per connection that reads ahead (§5.4): a command queued behind a held one is
known to the scheduler at once, so its operation counts as waiting, not running, and no timeout
is needed to move on. With one connection per operation nothing can queue behind a held
command, so reading ahead would only add a thread hop (about 2 ms per D3 execution).
"""

import hashlib
import queue
import socket
import threading
import time

from . import resp

def digest(data):
    return hashlib.sha256(data).hexdigest()[:16]


def nodelay(sock):
    """Valkey sets TCP_NODELAY on its own sockets, and so do the clients we test; without it,
    two small replies in a row on one connection wait for a delayed ACK (about 40 ms on Linux),
    a delay the service would never see without the proxy."""
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


class Held:
    def __init__(self, op, conn, name, key_digest):
        self.op, self.conn, self.name, self.key_digest = op, conn, name, key_digest
        self.permitted = False
        self.executed = False


class Controller:
    """State shared by proxy threads (which hold commands) and the decision loop (which permits them).

    Attribution (§5.3): with one connection per operation, a connection belongs to the
    operation that was running when its first gated command arrived. With ``shared_connections``
    (a multiplexed client), each command belongs to the operation running when it arrived; each
    decision lets at most one operation run, so that is the only one that can have sent it.

    A multiplexed client also locks its connection for a transaction: from writing WATCH or
    MULTI until it writes the closing EXEC, DISCARD or UNWATCH, no other operation can write
    (StackExchange.Redis does this; seen with MONITOR, experiments/2026-10-28-d1-gate). While
    the lock is held, the other operations are blocked in the client, not running. When the block
    closes, the one operation that was blocked writes next. If several were blocked, which one
    writes first is up to the client, so the execution cannot be attributed.
    """

    def __init__(self, delta_q, shared_connections=False):
        self.delta_q = delta_q
        self.shared_connections = shared_connections
        self.cv = threading.Condition()
        self.exec_lock = threading.Lock()
        self.active = False
        self.events = []
        self._seq = 0
        self.reset_round(0)

    def reset_round(self, n_ops):
        self.n_ops = n_ops
        self.admitted = set()
        self.done = set()
        self.held = {}        # op -> [Held], in arrival order
        self.queues = {}      # conn id -> [Held], in arrival order (the head is the next to run)
        self.conn_op = {}     # conn id -> op (one connection per operation)
        self.client_lock = {}  # shared conn id -> op whose transaction holds the client's connection
        self.resuming = {}     # shared conn id -> ops that were blocked by a transaction just closed
        self.running_op = None
        self.unattributed = 0

    def event(self, kind, **fields):
        self._seq += 1
        self.events.append({"seq": self._seq, "event": kind, **fields})

    # --- called by proxy connection threads -------------------------------------------------
    def _attribute(self, conn, name):
        if self.shared_connections:
            if conn in self.client_lock:
                self.event("write_during_client_lock", conn=conn, cmd=name)
                return None
            blocked = self.resuming.pop(conn, [])
            if len(blocked) == 1:
                return blocked[0]
            if blocked:
                self.event("ambiguous_resume", conn=conn, ops=blocked)
                return None
            op = self.running_op
            return op if op is not None and op not in self.done else None
        op = self.conn_op.get(conn)
        if op is None and self.running_op is not None:
            op = self.conn_op[conn] = self.running_op
        return op

    def arrive(self, conn, name, key_digest):
        """A gated command was read from a connection. Returns its ticket, or None in
        pass-through or when no operation can have sent it."""
        with self.cv:
            if not self.active:
                return None
            op = self._attribute(conn, name)
            if op is None:
                self.unattributed += 1
                self.event("unattributed", conn=conn, cmd=name)
                return None
            held = Held(op, conn, name, key_digest)
            self.held.setdefault(op, []).append(held)
            self.queues.setdefault(conn, []).append(held)
            self.event("arrive", op=op, conn=conn, cmd=name, key=key_digest)
            if self.shared_connections and name in resp.BLOCK_OPENERS:
                self.client_lock[conn] = op
            self.cv.notify_all()
            return held

    def block_closed(self, conn):
        """The client wrote a block's closing command, so its transaction lock is released."""
        with self.cv:
            owner = self.client_lock.pop(conn, None)
            if owner is not None and self.active:
                self.resuming[conn] = [k for k in sorted(self.admitted) if k != owner
                                       and k not in self.done and not self.held.get(k)]
                self.cv.notify_all()

    def wait_permit(self, held):
        """Block the connection at this command until the scheduler permits it."""
        with self.cv:
            while not held.permitted and self.active:
                self.cv.wait()

    def ungated(self, conn, name):
        """A command outside the gated set arrived during a round (checked by soundness)."""
        with self.cv:
            if self.active:
                self.event("ungated", conn=conn, cmd=name)

    def executed(self, held, args_digest, reply_digest):
        with self.cv:
            self.event("exec", op=held.op, conn=held.conn, cmd=held.name, key=held.key_digest,
                       args=args_digest, reply=reply_digest)
            held.executed = True
            for waiting in (self.held.get(held.op, []), self.queues.get(held.conn, [])):
                if held in waiting:
                    waiting.remove(held)
            self.cv.notify_all()

    # --- called by the decision loop --------------------------------------------------------
    def begin_round(self, n_ops):
        with self.cv:
            self.reset_round(n_ops)
            self.events = []
            self._seq = 0
            self.active = True

    def end_round(self):
        with self.cv:
            self.active = False
            self.cv.notify_all()

    def op_done(self, op):
        with self.cv:
            self.done.add(op)
            self.cv.notify_all()

    def admit(self, op):
        with self.cv:
            self.admitted.add(op)
            self.running_op = op
            self.event("admit", op=op)

    def permit(self, op):
        with self.cv:
            held = self.held[op][0]
            assert self.queues[held.conn][0] is held, "only a connection's head command can run"
            held.permitted = True
            self.running_op = op
            self.cv.notify_all()
            while not held.executed:
                self.cv.wait()

    def _running(self):
        owners = set(self.client_lock.values())  # with one shared connection, at most one
        return [k for k in self.admitted if k not in self.done and not self.held.get(k)
                and not (owners and k not in owners)]

    def wait_quiescent(self):
        """Block until no admitted operation is running. Returns True if Δq forced a decision."""
        deadline = time.monotonic() + self.delta_q
        with self.cv:
            while self._running():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return True
                self.cv.wait(remaining)
            return False

    def all_done(self):
        with self.cv:
            return len(self.done) == self.n_ops

    def choices(self):
        """Admit a pending operation, or run an operation's command at the head of its
        connection. On a shared connection a command behind another one cannot run yet."""
        with self.cv:
            admits = [f"admit:{k}" for k in range(self.n_ops) if k not in self.admitted]
            execs = [f"exec:{k}" for k in sorted(self.held)
                     if self.held[k] and self.queues[self.held[k][0].conn][0] is self.held[k][0]]
            return admits + execs

    def held_commands(self):
        with self.cv:
            return {k: hs[0].name for k, hs in self.held.items() if hs}


class Proxy:
    def __init__(self, listen, upstream, controller):
        self.listen, self.upstream, self.ctl = listen, upstream, controller
        self.passthrough_counts = {}
        self._conn_ids = 0
        self._lock = threading.Lock()

    def start(self):
        server = socket.create_server(self.listen)
        threading.Thread(target=self._accept, args=(server,), daemon=True).start()

    def _accept(self, server):
        while True:
            client, _ = server.accept()
            nodelay(client)
            with self._lock:
                self._conn_ids += 1
                conn_id = self._conn_ids
            threading.Thread(target=self._serve, args=(conn_id, client), daemon=True).start()

    def _count(self, name):
        with self._lock:
            self.passthrough_counts[name] = self.passthrough_counts.get(name, 0) + 1

    def _commands(self, conn_id, client):
        """Yield the client's commands in arrival order as (frame, name, gated, ticket),
        registering each gated one with the scheduler as it arrives. Blocks are tracked here,
        so a block's inner commands are never gated. A SUBSCRIBE frame carries the rest of the
        buffered bytes and ends the stream: the raw pump takes over."""
        inbuf, in_block = bytearray(), False
        while True:
            try:
                end = resp.frame_end(inbuf)
            except resp.Incomplete:
                chunk = client.recv(65536)
                if not chunk:
                    return
                inbuf += chunk
                continue
            frame = bytes(inbuf[:end])
            del inbuf[:end]
            parts = resp.command_parts(frame)
            name = resp.command_name(parts)
            if name in resp.PUBSUB:
                yield frame + bytes(inbuf), name, False, None
                return
            gated = (name in resp.GATED or name in resp.SCRIPTS
                     or name in resp.BLOCK_OPENERS) and not in_block
            held = self.ctl.arrive(conn_id, name, digest(resp.command_key(parts))) if gated else None
            if gated and name in resp.BLOCK_OPENERS:
                in_block = True
            elif in_block and name in resp.BLOCK_CLOSERS:
                in_block = False
                if self.ctl.shared_connections:
                    self.ctl.block_closed(conn_id)
            yield frame, name, gated, held

    def _read_ahead(self, conn_id, client, frames):
        try:
            for item in self._commands(conn_id, client):
                frames.put(item)
        except OSError:
            pass
        frames.put(None)

    def _serve(self, conn_id, client):
        upstream = socket.create_connection(self.upstream)
        nodelay(upstream)
        if self.ctl.shared_connections:
            frames = queue.Queue()
            threading.Thread(target=self._read_ahead, args=(conn_id, client, frames),
                             daemon=True).start()
            commands = iter(frames.get, None)
        else:  # read the next command only when the previous one is done, as before
            commands = self._commands(conn_id, client)
        upbuf = bytearray()
        in_block = False
        try:
            for frame, name, gated, held in commands:
                if name in resp.PUBSUB:
                    upstream.sendall(frame)
                    self._pump(client, upstream)
                    return

                if gated:
                    if held is not None:
                        self.ctl.wait_permit(held)
                    self.ctl.exec_lock.acquire()
                    if name in resp.BLOCK_OPENERS:
                        in_block = True  # keep the lock until the block closes
                elif not in_block:
                    self._count(name)
                    if name not in resp.HOUSEKEEPING:
                        self.ctl.ungated(conn_id, name)

                upstream.sendall(frame)
                reply = self._read_reply(upstream, upbuf, client)

                if gated and not in_block:
                    self.ctl.exec_lock.release()
                elif in_block and name in resp.BLOCK_CLOSERS:
                    in_block = False
                    self.ctl.exec_lock.release()
                if held is not None:
                    self.ctl.executed(held, digest(frame), digest(reply))
                client.sendall(reply)
        except OSError:
            return
        finally:
            if in_block:
                self.ctl.exec_lock.release()
            client.close()
            upstream.close()

    @staticmethod
    def _read_reply(sock, buf, client):
        """Next reply frame; RESP3 pushes met on the way are forwarded to the client as-is."""
        while True:
            try:
                end = resp.frame_end(buf)
            except resp.Incomplete:
                chunk = sock.recv(65536)
                if not chunk:
                    raise OSError("upstream closed")
                buf += chunk
                continue
            frame = bytes(buf[:end])
            del buf[:end]
            if resp.is_push(frame):
                client.sendall(frame)
                continue
            return frame

    @staticmethod
    def _pump(client, upstream):
        def copy(src, dst):
            try:
                while chunk := src.recv(65536):
                    dst.sendall(chunk)
            except OSError:
                pass
        threading.Thread(target=copy, args=(upstream, client), daemon=True).start()
        copy(client, upstream)
