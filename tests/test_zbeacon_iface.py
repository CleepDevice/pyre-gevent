"""Unit tests for ZBeacon interface selection and UDP readiness (issues 5-7)."""
import importlib.util
import ipaddress
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.modules.setdefault("zmq", MagicMock())
sys.modules.setdefault("zmq.green", MagicMock())

_pkg = type(sys)("pyre_gevent")
_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "pyre_gevent")]
sys.modules.setdefault("pyre_gevent", _pkg)
sys.modules.setdefault("pyre_gevent.zactor", MagicMock())

# Minimal netaddr 1.x stub (private IPv4 check)
class _IPAddress(object):
    def __init__(self, addr):
        self.addr = str(addr)

    def is_ipv4_private_use(self):
        return self.addr.startswith(("10.", "192.168.", "172.16.", "172.17.", "127."))

    def is_ipv6_unique_local(self):
        return False

    def __str__(self):
        return self.addr


_netaddr = MagicMock()
_netaddr.IPAddress = _IPAddress
_netaddr.__version__ = "1.3.0"
sys.modules["netaddr"] = _netaddr
sys.modules["netifaces"] = MagicMock()

_zhelper = MagicMock()
_zhelper.u = lambda x: x
sys.modules["pyre_gevent.zhelper"] = _zhelper

_path = Path(__file__).resolve().parents[1] / "pyre_gevent" / "zbeacon.py"
_spec = importlib.util.spec_from_file_location("pyre_gevent.zbeacon", _path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["pyre_gevent.zbeacon"] = _mod
_spec.loader.exec_module(_mod)
ZBeacon = _mod.ZBeacon
AF_INET = _mod.AF_INET
AF_PACKET = _mod.AF_PACKET
AF_LINK = _mod.AF_LINK


class ZBeaconIfaceTest(unittest.TestCase):
    def _beacon(self):
        beacon = ZBeacon.__new__(ZBeacon)
        beacon.udpsock = MagicMock()
        beacon.address = None
        beacon.mac = None
        beacon.network_address = None
        beacon.broadcast_address = None
        beacon.interface_name = None
        beacon.forced_interface = None
        beacon.udp_ready = False
        beacon.terminated = False
        beacon.pipe = MagicMock()
        beacon.port_nbr = 5670
        beacon.transmit = None
        return beacon

    def test_virtual_iface_detection(self):
        self.assertTrue(ZBeacon._is_virtual_iface("docker0"))
        self.assertTrue(ZBeacon._is_virtual_iface("br-abc123"))
        self.assertTrue(ZBeacon._is_virtual_iface("veth0"))
        self.assertFalse(ZBeacon._is_virtual_iface("eth0"))
        self.assertFalse(ZBeacon._is_virtual_iface("wlan0"))
        self.assertFalse(ZBeacon._is_virtual_iface("enp3s0"))

    def test_prepare_socket_accepts_macos_af_link_mac(self):
        beacon = self._beacon()
        netinf = [
            {
                "en0": {
                    AF_INET: {"addr": "192.168.1.20", "netmask": "255.255.255.0"},
                    AF_LINK: {"addr": "11:22:33:44:55:66"},
                }
            },
        ]
        with patch.object(_mod.zhelper, "get_ifaddrs", return_value=netinf), patch.object(
            beacon, "_ZBeacon__fill_gateways", return_value=(["en0"], [])
        ):
            beacon._prepare_socket()

        self.assertEqual(str(beacon.address), "192.168.1.20")
        self.assertEqual(beacon.interface_name, "en0")
        self.assertEqual(beacon.mac, "11:22:33:44:55:66")

    def test_prepare_socket_prefers_default_route(self):
        beacon = self._beacon()
        netinf = [
            {
                "docker0": {
                    AF_INET: {"addr": "172.17.0.1", "netmask": "255.255.0.0"},
                    AF_PACKET: {"addr": "02:42:00:00:00:01"},
                }
            },
            {
                "eth0": {
                    AF_INET: {"addr": "192.168.1.10", "netmask": "255.255.255.0"},
                    AF_PACKET: {"addr": "aa:bb:cc:dd:ee:ff"},
                }
            },
        ]
        with patch.object(_mod.zhelper, "get_ifaddrs", return_value=netinf), patch.object(
            beacon, "_ZBeacon__fill_gateways", return_value=(["eth0"], [])
        ):
            beacon._prepare_socket()

        self.assertEqual(str(beacon.address), "192.168.1.10")
        self.assertEqual(beacon.interface_name, "eth0")

    def test_prepare_socket_fallback_without_gateway(self):
        beacon = self._beacon()
        netinf = [
            {
                "eth0": {
                    AF_INET: {"addr": "192.168.1.10", "netmask": "255.255.255.0"},
                    AF_PACKET: {"addr": "aa:bb:cc:dd:ee:ff"},
                }
            },
        ]
        with patch.object(_mod.zhelper, "get_ifaddrs", return_value=netinf), patch.object(
            beacon, "_ZBeacon__fill_gateways", return_value=([], [])
        ):
            beacon._prepare_socket()

        self.assertEqual(str(beacon.address), "192.168.1.10")
        self.assertEqual(beacon.interface_name, "eth0")

    def test_prepare_socket_skips_virtual_without_gateway(self):
        beacon = self._beacon()
        netinf = [
            {
                "docker0": {
                    AF_INET: {"addr": "172.17.0.1", "netmask": "255.255.0.0"},
                    AF_PACKET: {"addr": "02:42:00:00:00:01"},
                }
            },
        ]
        with patch.object(_mod.zhelper, "get_ifaddrs", return_value=netinf), patch.object(
            beacon, "_ZBeacon__fill_gateways", return_value=([], [])
        ):
            beacon._prepare_socket()

        self.assertEqual(str(beacon.address), "127.0.0.1")
        self.assertEqual(beacon.interface_name, "loopback")

    def test_prepare_udp_returns_false_on_bind_error(self):
        beacon = self._beacon()
        beacon.broadcast_address = ipaddress.IPv4Address("192.168.1.255")
        beacon.address = "192.168.1.10"
        beacon.udpsock.bind.side_effect = OSError("bind failed")

        with patch.object(beacon, "_prepare_socket"):
            ok = beacon.prepare_udp()

        self.assertFalse(ok)
        self.assertFalse(beacon.udp_ready)

    def test_prepare_udp_returns_false_for_loopback(self):
        beacon = self._beacon()

        def fake_prepare(_iface=None):
            beacon.address = "127.0.0.1"
            beacon.broadcast_address = ipaddress.IPv4Address("225.25.25.25")

        with patch.object(beacon, "_prepare_socket", side_effect=fake_prepare):
            ok = beacon.prepare_udp()

        self.assertFalse(ok)
        self.assertFalse(beacon.udp_ready)

    def test_send_beacon_skipped_when_not_ready(self):
        beacon = self._beacon()
        beacon.udp_ready = False
        beacon.transmit = b"ZRE"
        beacon.broadcast_address = "192.168.1.255"
        beacon.send_beacon()
        self.assertFalse(beacon.udpsock.sendto.called)

    def test_configure_terminates_when_udp_not_ready(self):
        beacon = self._beacon()
        with patch.object(beacon, "prepare_udp", return_value=False):
            beacon.address = "192.168.1.10"
            beacon.configure("", 5670)

        self.assertTrue(beacon.terminated)
        self.assertEqual(str(beacon.address), "127.0.0.1")
        beacon.pipe.send_unicode.assert_called_with("127.0.0.1")

    def test_prepare_socket_honours_forced_interface(self):
        """Forced name must win even if another iface is the default route."""
        beacon = self._beacon()
        netinf = [
            {
                "eth0": {
                    AF_INET: {"addr": "192.168.1.10", "netmask": "255.255.255.0"},
                    AF_PACKET: {"addr": "aa:bb:cc:dd:ee:01"},
                }
            },
            {
                "wlan0": {
                    AF_INET: {"addr": "10.0.0.5", "netmask": "255.255.255.0"},
                    AF_PACKET: {"addr": "aa:bb:cc:dd:ee:02"},
                }
            },
        ]
        with patch.object(_mod.zhelper, "get_ifaddrs", return_value=netinf), patch.object(
            beacon, "_ZBeacon__fill_gateways", return_value=(["eth0"], [])
        ):
            beacon._prepare_socket("wlan0")

        self.assertEqual(beacon.interface_name, "wlan0")
        self.assertEqual(str(beacon.address), "10.0.0.5")

    def test_prepare_socket_forced_missing_falls_to_loopback(self):
        beacon = self._beacon()
        netinf = [
            {
                "eth0": {
                    AF_INET: {"addr": "192.168.1.10", "netmask": "255.255.255.0"},
                    AF_PACKET: {"addr": "aa:bb:cc:dd:ee:ff"},
                }
            },
        ]
        with patch.object(_mod.zhelper, "get_ifaddrs", return_value=netinf), patch.object(
            beacon, "_ZBeacon__fill_gateways", return_value=(["eth0"], [])
        ):
            beacon._prepare_socket("does-not-exist")

        self.assertEqual(beacon.interface_name, "loopback")
        self.assertEqual(str(beacon.address), "127.0.0.1")

    def test_prepare_socket_forced_allows_virtual_iface(self):
        beacon = self._beacon()
        netinf = [
            {
                "docker0": {
                    AF_INET: {"addr": "172.17.0.1", "netmask": "255.255.0.0"},
                    AF_PACKET: {"addr": "02:42:00:00:00:01"},
                }
            },
        ]
        with patch.object(_mod.zhelper, "get_ifaddrs", return_value=netinf), patch.object(
            beacon, "_ZBeacon__fill_gateways", return_value=([], [])
        ):
            beacon._prepare_socket("docker0")

        self.assertEqual(beacon.interface_name, "docker0")
        self.assertEqual(str(beacon.address), "172.17.0.1")

    def test_prepare_udp_uses_forced_interface_attribute(self):
        beacon = self._beacon()
        beacon.forced_interface = "eth0"
        prepared = []

        def fake_prepare(iface=None):
            prepared.append(iface)
            beacon.address = "192.168.1.10"
            beacon.broadcast_address = ipaddress.IPv4Address("192.168.1.255")

        with patch.object(beacon, "_prepare_socket", side_effect=fake_prepare):
            ok = beacon.prepare_udp()

        self.assertTrue(ok)
        self.assertEqual(prepared, ["eth0"])


if __name__ == "__main__":
    unittest.main()
