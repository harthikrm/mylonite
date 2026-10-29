"""Tests for what D1 added: the cart contract's invariant, shared-connection attribution in the
controller, and the cart adapter's message encoding. Standard library only (no gRPC needed)."""

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mylonite import oracle  # noqa: E402
from mylonite.proxy import Controller  # noqa: E402

CLAUSE = {"id": "no_lost_quantity", "kind": "item_quantity_conserved", "op": "AddItem",
          "owner_arg": "user_id", "item_arg": "product_id", "amount_arg": "quantity",
          "reset_op": "EmptyCart"}


def add(product, quantity, status="ok", user="u1"):
    return {"op": "AddItem", "args": {"user_id": user, "product_id": product, "quantity": quantity},
            "status": status}


def empty(status="ok", user="u1"):
    return {"op": "EmptyCart", "args": {"user_id": user}, "status": status}


def failures(ops, pre, post):
    return oracle.item_quantity_conserved(CLAUSE, ops, pre, post)


class CartInvariantTest(unittest.TestCase):
    def test_lost_quantity_is_a_violation(self):
        self.assertTrue(failures([add("p", 1), add("p", 1)], {"u1": {}}, {"u1": {"p": 1}}))
        self.assertFalse(failures([add("p", 1), add("p", 1)], {"u1": {}}, {"u1": {"p": 2}}))

    def test_vanished_item_is_a_violation(self):
        found = failures([add("p", 1), add("q", 2)], {"u1": {}}, {"u1": {"q": 2}})
        self.assertEqual([f["key"] for f in found], ["u1/p"])

    def test_existing_quantity_counts(self):
        self.assertFalse(failures([add("p", 2)], {"u1": {"p": 3}}, {"u1": {"p": 5}}))
        self.assertTrue(failures([add("p", 2)], {"u1": {"p": 3}}, {"u1": {"p": 2}}))

    def test_info_may_or_may_not_apply(self):
        ops = [add("p", 1), add("p", 2, status="info")]
        for final in (1, 3):
            self.assertFalse(failures(ops, {"u1": {}}, {"u1": {"p": final}}))
        self.assertTrue(failures(ops, {"u1": {}}, {"u1": {"p": 2}}))

    def test_empty_cart_allows_every_serial_outcome(self):
        ops = [add("p", 1), empty()]
        for final in (0, 1):  # add then empty; empty then add
            self.assertFalse(failures(ops, {"u1": {"p": 1}}, {"u1": {"p": final}}))
        # an item that survived EmptyCart with its old quantity: no serial order gives 2
        self.assertTrue(failures(ops, {"u1": {"p": 1}}, {"u1": {"p": 2}}))

    def test_info_empty_cart_may_or_may_not_apply(self):
        ops = [add("p", 1), empty(status="info")]
        for final in (0, 1, 2):
            self.assertFalse(failures(ops, {"u1": {"p": 1}}, {"u1": {"p": final}}))

    def test_reset_with_no_effect_is_ignored(self):
        self.assertTrue(failures([add("p", 1), empty(status="fail")], {"u1": {"p": 1}}, {"u1": {"p": 0}}))

    def test_other_users_are_independent(self):
        ops = [add("p", 1, user="u1"), add("p", 1, user="u2")]
        self.assertFalse(failures(ops, {"u1": {}, "u2": {}}, {"u1": {"p": 1}, "u2": {"p": 1}}))


class SharedConnectionTest(unittest.TestCase):
    def run_permit(self, ctl, op):
        """``permit`` waits for the proxy to execute the command; play the proxy's part."""
        thread = threading.Thread(target=ctl.permit, args=(op,))
        thread.start()
        held = ctl.held[op][0]
        ctl.wait_permit(held)
        ctl.executed(held, "a", "r")
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_commands_belong_to_the_running_operation(self):
        ctl = Controller(delta_q=1, shared_connections=True)
        ctl.begin_round(2)
        ctl.admit(0)
        ctl.arrive(7, "HGET", "k")
        ctl.admit(1)
        ctl.arrive(7, "HGET", "k")  # same connection, behind op 0's command
        self.assertEqual(ctl.held_commands(), {0: "HGET", 1: "HGET"})
        self.assertEqual(ctl.choices(), ["exec:0"])  # op 1's command is not at the head
        self.assertFalse(ctl.wait_quiescent())      # both wait at the proxy: no timeout needed
        self.run_permit(ctl, 0)
        self.assertEqual(ctl.choices(), ["exec:1"])
        ctl.arrive(7, "HMSET", "k")                  # op 0 is the one running again
        self.assertEqual(ctl.held[0][0].name, "HMSET")
        self.assertEqual(ctl.choices(), ["exec:1"])  # behind op 1's HGET
        ctl.end_round()

    def test_per_connection_attribution_is_unchanged(self):
        ctl = Controller(delta_q=1)
        ctl.begin_round(2)
        ctl.admit(0)
        ctl.arrive(3, "GET", "k")
        ctl.admit(1)
        ctl.arrive(4, "GET", "k")
        self.assertEqual(sorted(ctl.choices()), ["exec:0", "exec:1"])
        self.run_permit(ctl, 0)
        ctl.arrive(3, "SET", "k")  # connection 3 is op 0's, whichever operation ran last
        self.assertEqual(ctl.held[0][0].name, "SET")
        ctl.end_round()

    def test_command_with_no_running_operation_is_unattributed(self):
        ctl = Controller(delta_q=1, shared_connections=True)
        ctl.begin_round(1)
        self.assertIsNone(ctl.arrive(7, "HGET", "k"))
        self.assertEqual([e["event"] for e in ctl.events], ["unattributed"])
        ctl.end_round()


class CartCodecTest(unittest.TestCase):
    def setUp(self):
        try:
            from mylonite.adapters import otel_cart
        except ImportError:  # grpcio lives in the D1 executor image, not necessarily on the host
            self.skipTest("grpcio not installed")
        self.cart = otel_cart

    def test_add_item_request_bytes(self):
        # AddItemRequest{user_id: "u1", item: CartItem{product_id: "P", quantity: 3}}
        self.assertEqual(self.cart.encode_add("u1", "P", 3), b"\n\x02u1\x12\x05\n\x01P\x10\x03")

    def test_cart_decoding(self):
        item = lambda p, q: b"\x12" + bytes([len(self.cart._field(1, 2, p) + self.cart._field(2, 0, q))]) \
            + self.cart._field(1, 2, p) + self.cart._field(2, 0, q)
        data = self.cart._field(1, 2, b"u1") + item(b"P", 2) + item(b"Q", 1) + item(b"P", 1)
        self.assertEqual(self.cart.decode_cart(data), {"P": 3, "Q": 1})
        self.assertEqual(self.cart.decode_cart(item(b"P", -1)), {"P": -1})
        self.assertEqual(self.cart.decode_cart(b""), {})


if __name__ == "__main__":
    unittest.main()
