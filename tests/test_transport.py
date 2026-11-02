"""Tests for the model client's transport errors (AM-002): a local server fails the request at each
phase, and every failure must reach the pre-registered retry rule as a retryable ModelAPIError.
No request leaves 127.0.0.1."""

import importlib.util
import json
import socket
import struct
import sys
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mylonite import planner  # noqa: E402

_spec = importlib.util.spec_from_file_location("run_pilot", ROOT / "experiments/2026-10-29-pilot/run_pilot.py")
pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot)

ANSWER = json.dumps({"model": "muse-spark-1.3", "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                     "choices": [{"message": {"content": json.dumps({"experiments": []})}}]}).encode()


def reply(status, body, length=None):
    head = (f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body) if length is None else length}\r\n\r\n")
    return head.encode() + body


def reset(conn):
    """Close with RST instead of FIN."""
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    conn.close()


def stall(conn):
    conn.sendall(reply("200 OK", ANSWER[:20], len(ANSWER)))
    time.sleep(1.5)  # longer than the client's timeout in these tests
    conn.close()


MODES = {
    "reset_before_response": lambda c: reset(c),
    "close_before_response": lambda c: c.close(),
    "reset_mid_body": lambda c: (c.sendall(reply("200 OK", ANSWER[:20], len(ANSWER))), reset(c)),
    "short_body": lambda c: (c.sendall(reply("200 OK", ANSWER[:20], len(ANSWER))), c.close()),
    "timeout_mid_body": stall,
    "not_utf8": lambda c: (c.sendall(reply("200 OK", b'{"a": "\xff\xfe"}')), c.close()),
    "not_an_object": lambda c: (c.sendall(reply("200 OK", b"[]")), c.close()),
    "error_503_short_body": lambda c: (c.sendall(reply("503 Service Unavailable", b"busy", 100)), c.close()),
    "error_429": lambda c: (c.sendall(reply("429 Too Many Requests", b'{"error": "slow down"}')), c.close()),
    "error_400": lambda c: (c.sendall(reply("400 Bad Request", b'{"error": "bad"}')), c.close()),
    "ok": lambda c: (c.sendall(reply("200 OK", ANSWER)), c.close()),
}


class Server:
    """Answers one connection per mode, in order, after reading the whole request."""

    def __init__(self, modes):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.sock.settimeout(10)
        self.port = self.sock.getsockname()[1]
        self.errors = []
        self.thread = threading.Thread(target=self.serve, args=(list(modes),), daemon=True)
        self.thread.start()

    def read_request(self, conn):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                raise ConnectionError("the client closed before sending a whole request")
            data += chunk
        head, _, body = data.partition(b"\r\n\r\n")
        length = int(next(line.split(b":")[1] for line in head.split(b"\r\n")
                          if line.lower().startswith(b"content-length")))
        while len(body) < length:
            chunk = conn.recv(65536)
            if not chunk:
                raise ConnectionError("the client closed before sending a whole request")
            body += chunk

    def serve(self, modes):
        try:
            for mode in modes:
                conn, _ = self.sock.accept()
                conn.settimeout(10)
                self.read_request(conn)
                MODES[mode](conn)
        except Exception as exc:  # reported by finish()
            self.errors.append(exc)
        finally:
            self.sock.close()

    def finish(self, test):
        self.thread.join(10)
        test.assertFalse(self.thread.is_alive(), "the test server did not finish")
        test.assertEqual(self.errors, [])


class TransportErrors(unittest.TestCase):
    def setUp(self):
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
        self.addCleanup(urllib.request.install_opener, None)

    def call(self, *modes, timeout=10):
        server = Server(modes)
        with mock.patch.object(planner, "BASE_URL", f"http://127.0.0.1:{server.port}"):
            try:
                return planner.call_muse("test-key", {"messages": []}, timeout=timeout)
            finally:
                server.finish(self)

    def assert_transport(self, mode, kind, status=None, timeout=10):
        with self.assertRaises(planner.ModelAPIError) as caught:
            self.call(mode, timeout=timeout)
        self.assertEqual(caught.exception.status, status)
        self.assertTrue(caught.exception.retryable, str(caught.exception))
        self.assertIn(kind, str(caught.exception))
        self.assertNotIn("test-key", str(caught.exception))

    def test_every_phase_is_a_retryable_transport_error(self):
        for mode, kind in (("reset_before_response", "ConnectionResetError"),
                           ("close_before_response", "RemoteDisconnected"),
                           ("reset_mid_body", "ConnectionResetError"),
                           ("short_body", "IncompleteRead"),
                           ("not_utf8", "UnicodeDecodeError"),
                           ("not_an_object", "not an object")):
            with self.subTest(mode=mode):
                self.assert_transport(mode, kind)

    def test_a_timeout_while_reading_is_still_a_transport_error(self):
        self.assert_transport("timeout_mid_body", "TimeoutError", timeout=0.5)

    def test_an_error_status_with_an_unreadable_body_keeps_its_status(self):
        self.assert_transport("error_503_short_body", "error body unreadable: IncompleteRead", status=503)

    def test_rate_limits_are_still_retried_and_client_errors_are_not(self):
        self.assert_transport("error_429", "slow down", status=429)
        with self.assertRaises(planner.ModelAPIError) as caught:
            self.call("error_400")
        self.assertEqual(caught.exception.status, 400)
        self.assertFalse(caught.exception.retryable)

    def test_an_answer_still_parses(self):
        plan, meta = self.call("ok")
        self.assertEqual(plan, {"experiments": []})
        self.assertEqual(meta["model"], "muse-spark-1.3")

    def test_the_retry_rule_now_covers_a_reset(self):
        logged = []
        model = pilot.LiveModel("test-key", {"model_cost_cap_usd": 30.0,
                                             "prices": {"input": 1.25, "cached": 0.15, "output": 4.25}},
                                logged.append)
        server = Server(["reset_before_response", "ok"])
        with mock.patch.object(planner, "BASE_URL", f"http://127.0.0.1:{server.port}"), \
                mock.patch.object(pilot.time, "sleep") as sleep:
            plan, meta = model({"messages": []}, 1)
        server.finish(self)
        self.assertEqual(plan, {"experiments": []})
        self.assertEqual(sleep.call_args_list, [mock.call(5)])
        self.assertEqual([e.get("failed_attempt") for e in logged], [1, None])
        self.assertIn("ConnectionResetError", meta["failed_attempts"][0])


if __name__ == "__main__":
    unittest.main()
