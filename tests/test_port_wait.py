from __future__ import annotations

import socket
import sys
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

from engines import port_in_use, wait_for_free_ports  # noqa: E402


def listener() -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


def unused_port() -> int:
    sock, port = listener()
    sock.close()
    return port


class PortWaitTests(unittest.TestCase):
    def test_a_free_port_is_reported_free(self) -> None:
        self.assertFalse(port_in_use(unused_port()))

    def test_a_listening_port_is_reported_in_use(self) -> None:
        sock, port = listener()
        try:
            self.assertTrue(port_in_use(port))
        finally:
            sock.close()

    def test_free_ports_return_immediately(self) -> None:
        start = time.monotonic()
        waited = wait_for_free_ports([unused_port(), unused_port()], timeout_s=5, poll_s=0.05)
        self.assertLess(time.monotonic() - start, 1.0)
        self.assertEqual(waited, 0.0)

    def test_it_waits_until_the_previous_owner_releases_the_port(self) -> None:
        sock, port = listener()
        threading.Timer(0.4, sock.close).start()
        waited = wait_for_free_ports([port], timeout_s=5, poll_s=0.05)
        self.assertGreaterEqual(waited, 0.3)
        self.assertLess(waited, 3.0)

    def test_it_raises_when_the_port_stays_busy(self) -> None:
        sock, port = listener()
        try:
            with self.assertRaises(RuntimeError) as caught:
                wait_for_free_ports([port], timeout_s=0.3, poll_s=0.05)
            self.assertIn(str(port), str(caught.exception))
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
