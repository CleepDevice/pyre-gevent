import unittest
import sys
sys.path.append('../')
import pyre_gevent as pyre
import zmq
import time
import logging
import sys


if sys.version.startswith('3'):
    unicode = str


class PyreTest(unittest.TestCase):
    def setUp(self, *args, **kwargs):
        self.ctx = zmq.Context()
        self.node1 = pyre.Pyre("node1", ctx=self.ctx)
        self.node1.set_header("X-TEST", "1")
        self.node2 = pyre.Pyre("node2", ctx=self.ctx)
        self.node2.set_header("X-TEST", "1")
        self.node1.start()
        self.node2.start()
        # Wait until peers see each other, then drain ENTER so later asserts
        # are not racing leftover discovery events.
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if self.node1.peers() and self.node2.peers():
                break
            time.sleep(0.05)
        self.assertTrue(self.node1.peers(), "node1 did not discover node2")
        self.assertTrue(self.node2.peers(), "node2 did not discover node1")
        self._drain(self.node1)
        self._drain(self.node2)
    # end setUp

    def tearDown(self):
        self.node1.stop()
        self.node2.stop()
    # end tearDown

    def _drain(self, node, timeout=0.5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if node.socket().getsockopt(zmq.EVENTS) & zmq.POLLIN:
                node.recv()
            else:
                time.sleep(0.02)

    def _recv_type(self, node, expected, timeout=5.0):
        """Receive until a message of the expected type (skip earlier events)."""
        if not isinstance(expected, (list, tuple, set)):
            expected = (expected,)
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            if node.socket().getsockopt(zmq.EVENTS) & zmq.POLLIN:
                last = node.recv()
                if last[0] in expected:
                    return last
                continue
            time.sleep(0.05)
        self.fail("timeout waiting for %r (last=%r)" % (expected, last))

    def test_get_name(self):
        self.assertEqual("node1", self.node1.name())
        self.assertEqual("node2", self.node2.name())
    # end test_get_name

    def test_get_peers(self):
        id1 = self.node1.uuid()
        peers = self.node2.peers()

        self.assertIsInstance(peers, list)
        self.assertIn(id1, peers)
    # end test_get_peers

    def test_get_peers_by_group(self):
        id1 = self.node1.uuid()
        self.node1.join("TEST")
        # pyre works asynchronous so give some time to let changes disperse
        time.sleep(0.5)

        peers = self.node2.peers_by_group("TEST")
        self.node1.leave("TEST")

        self.assertIsInstance(peers, list)
        self.assertIn(id1, peers)
    # end test_get_peers

    def test_get_peer_address(self):
        id1 = self.node1.uuid()
        id2 = self.node2.uuid()

        self.assertIsInstance(self.node1.peer_address(id2), unicode)
        self.assertIsInstance(self.node2.peer_address(id1), unicode)
    # end test_get_peer_address

    def test_peer_header_value(self):
        id1 = self.node1.uuid()
        id2 = self.node2.uuid()

        self.assertEqual("1", self.node1.peer_header_value(id2, "X-TEST"))
        self.assertEqual("1", self.node2.peer_header_value(id1, "X-TEST"))
    # end test_get_peer_header_value

    def test_get_own_groups(self):
        self.node1.join("TEST")
        self.node2.join("TEST")
        # pyre works asynchronous so give some time to let changes disperse
        time.sleep(0.5)

        self.assertIn("TEST", self.node1.own_groups())
        self.assertIn("TEST", self.node2.own_groups())
    # end test_get_own_groups

    def test_join_leave_msg(self):
        self.node1.join("TEST")
        self.node2.join("TEST")
        self.assertEqual(self._recv_type(self.node1, b"JOIN")[0], b"JOIN")
        self.assertEqual(self._recv_type(self.node2, b"JOIN")[0], b"JOIN")
        self.node1.leave("TEST")
        self.node2.leave("TEST")
        self.assertEqual(self._recv_type(self.node1, b"LEAVE")[0], b"LEAVE")
        self.assertEqual(self._recv_type(self.node2, b"LEAVE")[0], b"LEAVE")

    def test_get_peer_groups(self):
        self.node1.join("TEST")
        self.node2.join("TEST")

        # pyre works asynchronous so give some time to let changes disperse
        time.sleep(0.5)

        self.assertIn("TEST", self.node1.peer_groups())
        self.assertIn("TEST", self.node2.peer_groups())
    # end test_get_peer_groups

    def test_whispers(self):
        self.node1.whispers(self.node2.uuid(), "Hi")
        msg = self._recv_type(self.node2, b"WHISPER")
        self.assertEqual(b"WHISPER", msg[0])
        self.assertEqual(self.node1.uuid().bytes, msg[1])
        self.assertEqual(b"node1", msg[2])
        self.assertEqual(b"Hi", msg[3])

    def test_shouts(self):
        self.node1.join("TEST")
        self.node2.join("TEST")
        self._recv_type(self.node1, b"JOIN")
        self._recv_type(self.node2, b"JOIN")
        self.node1.shouts("TEST", "Hi")
        msg = self._recv_type(self.node2, b"SHOUT")
        self.assertEqual(b"SHOUT", msg[0])
        self.assertEqual(self.node1.uuid().bytes, msg[1])
        self.assertEqual(b"node1", msg[2])
        self.assertEqual(b"TEST", msg[3])
        self.assertEqual(b"Hi", msg[4])

    def test_shout(self):
        self.node1.join("TEST")
        self.node2.join("TEST")
        self._recv_type(self.node1, b"JOIN")
        self._recv_type(self.node2, b"JOIN")
        self.node1.shout("TEST", b"Hi")
        msg = self._recv_type(self.node2, b"SHOUT")
        self.assertEqual(b"SHOUT", msg[0])
        self.assertEqual(self.node1.uuid().bytes, msg[1])
        self.assertEqual(b"node1", msg[2])
        self.assertEqual(b"TEST", msg[3])
        self.assertEqual(b"Hi", msg[4])

    def test_zfinal(self):
        global inst_count
        inst_count = 1
        self.assertTrue(True)
    # end test_zfinal
# end PyreTest

if __name__ == '__main__':
    inst_count = 0

    logger = logging.getLogger("pyre")
    logger.setLevel(logging.DEBUG)

    try:
        unittest.main()
    except Exception as a:
        print(a)
