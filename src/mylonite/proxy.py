"""Delay-only RESP2 proxy and the shared scheduling state (ARCHITECTURE.md §5).

One thread per client connection, each with its own upstream connection. A connection's
commands are handled strictly in arrival order, so per-connection order can never be broken;
the scheduler can only decide *when* a connection's head command runs, and which connection
goes next. A single lock keeps at most one gated command (or block) in flight to the store.
"""

import hashlib
import socket
import threading
import time

from . import resp

def digest(data):
    return hashlib.sha256(data).hexdigest()[:16]


class Held:
    def __init__(self, op, conn, name, key_digest):
        self.op, self.conn, self.name, self.key_digest = op, conn, name, key_digest
        self.permitted = False
        self.executed = False


class Controller:
    """State shared by proxy threads (which hold commands) and the decision loop (which permits them)."""

    def __init__(self, delta_q):
        self.delta_q = delta_q
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
        self.held = {}        # op -> Held
        self.conn_op = {}     # conn id -> op
        self.running_op = None
        self.unattributed = 0

    def event(self, kind, **fields):
        self._seq += 1
        self.events.append({"seq": self._seq, "event": kind, **fields})

    # --- called by proxy connection threads -------------------------------------------------
    def gate(self, conn, name, key_digest):
        """Hold a gated command until the scheduler permits it. Returns None in pass-through."""
        with self.cv:
            if not self.active:
                return None
            op = self.conn_op.get(conn)
            if op is None:
                op = self.running_op
                if op is None:
                    self.unattributed += 1
                    self.event("unattributed", conn=conn, cmd=name)
                    return None
                self.conn_op[conn] = op
            held = Held(op, conn, name, key_digest)
            self.held[op] = held
            self.event("arrive", op=op, conn=conn, cmd=name, key=key_digest)
            self.cv.notify_all()
            while not held.permitted and self.active:
                self.cv.wait()
            return held

    def executed(self, held, args_digest, reply_digest):
        with self.cv:
            self.event("exec", op=held.op, conn=held.conn, cmd=held.name, key=held.key_digest,
                       args=args_digest, reply=reply_digest)
            held.executed = True
            if self.held.get(held.op) is held:
                del self.held[held.op]
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
            held = self.held[op]
            held.permitted = True
            self.running_op = op
            self.cv.notify_all()
            while not held.executed:
                self.cv.wait()

    def _running(self):
        return [k for k in self.admitted if k not in self.done and k not in self.held]

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
        with self.cv:
            admits = [f"admit:{k}" for k in range(self.n_ops) if k not in self.admitted]
            execs = [f"exec:{k}" for k in sorted(self.held)]
            return admits + execs

    def held_commands(self):
        with self.cv:
            return {k: h.name for k, h in self.held.items()}


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
            with self._lock:
                self._conn_ids += 1
                conn_id = self._conn_ids
            threading.Thread(target=self._serve, args=(conn_id, client), daemon=True).start()

    def _count(self, name):
        with self._lock:
            self.passthrough_counts[name] = self.passthrough_counts.get(name, 0) + 1

    def _serve(self, conn_id, client):
        upstream = socket.create_connection(self.upstream)
        inbuf, upbuf = bytearray(), bytearray()
        in_block = False
        try:
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
                    upstream.sendall(frame)
                    self._pump(client, upstream)
                    return

                gated = (name in resp.GATED or name in resp.SCRIPTS
                         or name in resp.BLOCK_OPENERS) and not in_block
                held = None
                if gated:
                    key = parts[1] if len(parts) > 1 else b""
                    held = self.ctl.gate(conn_id, name, digest(key))
                    self.ctl.exec_lock.acquire()
                    if name in resp.BLOCK_OPENERS:
                        in_block = True  # keep the lock until the block closes
                elif not in_block:
                    self._count(name)

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
