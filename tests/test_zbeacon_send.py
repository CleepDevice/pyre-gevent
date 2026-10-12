"""Unit tests for ZBeacon send resilience (no suicide on transient network errors)."""
import errno
import logging
import socket
import sys
import unittest
from unittest.mock import MagicMock, Mock

# Allow import on hosts without pyzmq / netifaces installed
sys.modules.setdefault("zmq", MagicMock())
sys.modules.setdefault("zmq.green", MagicMock())
sys.modules.setdefault("netifaces", MagicMock())
sys.modules.setdefault("netaddr", MagicMock())

sys.path.append("../")
from pyre_gevent.zbeacon import ZBeacon, _TRANSIENT_SEND_ERRNOS


class ZBeaconSendTest(unittest.TestCase):
    def _make_beacon(self):
        beacon = ZBeacon.__new__(ZBeacon)
        beacon.udpsock = Mock()
        beacon.transmit = b"ZRE"
        beacon.broadcast_address = "192.168.1.255"
        beacon.port_nbr = 5670
        beacon.terminated = False
        return beacon

    def test_transient_errnos_include_portable_values(self):
        self.assertIn(errno.ENETDOWN, _TRANSIENT_SEND_ERRNOS)
        self.assertIn(errno.ENETUNREACH, _TRANSIENT_SEND_ERRNOS)

    def test_send_beacon_keeps_alive_on_enetdown(self):
        beacon = self._make_beacon()
        err = OSError("Network is down")
        err.errno = errno.ENETDOWN
        beacon.udpsock.sendto.side_effect = err

        beacon.send_beacon()

        self.assertFalse(beacon.terminated)

    def test_send_beacon_keeps_alive_on_other_oserror(self):
        beacon = self._make_beacon()
        err = OSError("Other error")
        err.errno = errno.EPERM
        beacon.udpsock.sendto.side_effect = err

        beacon.send_beacon()

        self.assertFalse(beacon.terminated)

    def test_send_beacon_keeps_alive_on_socket_error(self):
        beacon = self._make_beacon()
        beacon.udpsock.sendto.side_effect = socket.error("send failed")

        beacon.send_beacon()

        self.assertFalse(beacon.terminated)


if __name__ == "__main__":
    logging.basicConfig(level=logging.CRITICAL)
    unittest.main()
