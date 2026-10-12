import unittest
import zmq
import struct
import uuid
import logging
import socket
import sys

sys.path.append("../")
from pyre_gevent.zactor import ZActor
from pyre_gevent.zbeacon import ZBeacon


def _configure_beacon(actor, port, interface=None):
    """Configure beacon; optional interface via SET INTERFACE (upstream style)."""
    if interface:
        if isinstance(interface, bytes):
            interface = interface.decode("utf-8")
        actor.send_unicode("SET INTERFACE", zmq.SNDMORE)
        actor.send_unicode(interface)
    actor.send_unicode("CONFIGURE", zmq.SNDMORE)
    actor.send(struct.pack("I", port))
    return actor.recv_unicode()


class ZBeaconTest(unittest.TestCase):
    def setUp(self, *args, **kwargs):
        ctx = zmq.Context()
        # two beacon frames
        self.transmit1 = struct.pack(
            "cccb16sH",
            b"Z",
            b"R",
            b"E",
            1,
            uuid.uuid4().bytes,
            socket.htons(9999),
        )
        self.transmit2 = struct.pack(
            "cccb16sH",
            b"Z",
            b"R",
            b"E",
            1,
            uuid.uuid4().bytes,
            socket.htons(9999),
        )

        self.node1 = ZActor(ctx, ZBeacon)
        self.node1.send_unicode("VERBOSE")
        hostname1 = _configure_beacon(self.node1, 9999)
        print("Hostname 1:", hostname1)

        self.node2 = ZActor(ctx, ZBeacon)
        self.node2.send_unicode("VERBOSE")
        hostname2 = _configure_beacon(self.node2, 9999)
        print("Hostname 2:", hostname2)

        # Beacon refuses 127.0.0.1 (no usable LAN iface) — skip integration tests
        if hostname1 in ("127.0.0.1", "None") or hostname2 in ("127.0.0.1", "None"):
            self.node1.destroy()
            self.node2.destroy()
            self.node1 = None
            self.node2 = None
            self.skipTest("No usable LAN interface for ZBeacon integration test")

    def tearDown(self):
        if getattr(self, "node1", None) is not None:
            self.node1.destroy()
        if getattr(self, "node2", None) is not None:
            self.node2.destroy()

    def test_publish_node1(self):
        self.node1.send_unicode("PUBLISH", zmq.SNDMORE)
        self.node1.send(self.transmit1)

    def test_publish_node2(self):
        self.node2.send_unicode("PUBLISH", zmq.SNDMORE)
        self.node2.send(self.transmit2)

    def test_recv_beacon_on_node1(self):
        self.node1.send_unicode("PUBLISH", zmq.SNDMORE)
        self.node1.send(self.transmit1)
        self.node2.send_unicode("PUBLISH", zmq.SNDMORE)
        self.node2.send(self.transmit2)
        req = self.node1.recv_multipart()
        self.assertEqual(self.transmit2, req[1])

    def test_recv_beacon_on_node2(self):
        self.node1.send_unicode("PUBLISH", zmq.SNDMORE)
        self.node1.send(self.transmit1)
        self.node2.send_unicode("PUBLISH", zmq.SNDMORE)
        self.node2.send(self.transmit2)
        req = self.node2.recv_multipart()
        self.assertEqual(self.transmit1, req[1])


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    logger.addHandler(ch)
    logging.getLogger("pyre.zbeacon2").setLevel(logging.DEBUG)

    try:
        unittest.main()
    except Exception as a:
        print(a)
