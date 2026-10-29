"""THREAT_MODEL.md §8: the sandbox launcher's flag set is static and reviewed. These tests fail
if a flag is dropped or loosened; any change to them is a security review item."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mylonite import sandbox  # noqa: E402


class FlagTest(unittest.TestCase):
    def test_locked_down_flags(self):
        self.assertEqual(sandbox.LOCKED_DOWN, ["--read-only", "--cap-drop", "ALL", "--security-opt",
                                               "no-new-privileges", "--pids-limit", "256", "--cpus", "1"])
        self.assertEqual(sandbox.limits("160m"), ["--memory", "160m", "--memory-swap", "160m"])

    def test_service_container(self):
        calls = []
        original = sandbox.docker
        sandbox.docker = lambda *args, **kw: calls.append(list(args))
        try:
            box = sandbox.Sandbox("t", Path("/nonexistent"))
            box.start_service("cart", "img", {"A": "1"}, "160m", "1654:1654")
        finally:
            sandbox.docker = original
        args = calls[0]
        self.assertEqual(args[:5], ["run", "-d", "--name", "t-cart", "--network"])
        self.assertEqual(args[5], "t-net")
        for flag in sandbox.LOCKED_DOWN + sandbox.limits("160m"):
            self.assertIn(flag, args)
        self.assertNotIn("-v", args)
        self.assertNotIn("--privileged", args)
        self.assertFalse(any(a.startswith(("-p", "--publish", "--cap-add", "--network=host")) for a in args))
        self.assertEqual(args[args.index("--user") + 1], "1654:1654")
        self.assertEqual(args[args.index("--env-file") + 1], "/dev/null")  # env is the explicit list only
        self.assertEqual(args[-1], "img")

    def test_executor_mounts_are_read_only(self):
        box = sandbox.Sandbox("t", Path("/repo"))
        cmd = box.executor_command("t-exec")
        mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]
        self.assertEqual(mounts, ["/repo/src:/app/src:ro", "/repo/fixtures:/app/fixtures:ro"])
        for flag in sandbox.HARDENED:
            self.assertIn(flag, cmd)


if __name__ == "__main__":
    unittest.main()
