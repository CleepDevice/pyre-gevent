# ======================================================================
#  zbeacon - LAN discovery and presence
#
#  Copyright (c) the Contributors as noted in the AUTHORS file.
#  This file is part of CZMQ, the high-level C binding for 0MQ:
#  http://czmq.zeromq.org.
#
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
    The zbeacon class implements a peer-to-peer discovery service for local
    networks. A beacon can broadcast and/or capture service announcements
    using UDP messages on the local area network. This implementation uses
    IPv4 UDP broadcasts. You can define the format of your outgoing beacons,
    and set a filter that validates incoming beacons. Beacons are sent and
    received asynchronously in the background.

    This class replaces zbeacon_v2, and is meant for applications that use
    the CZMQ v3 API (meaning, zsock).
"""

import errno
import logging
import ipaddress
import socket
import zmq.green as zmq
import struct
import time
from sys import platform
from .zactor import ZActor
from . import zhelper
from .zhelper import u
import netifaces # netiface-plus package
import netaddr
import re

logger = logging.getLogger(__name__)

INTERVAL_DFLT = 1.0
BEACON_MAX = 255  # Max size of beacon data
MULTICAST_GRP = "225.25.25.25"
# Transient network errors: keep beacon alive and retry (use portable errno values —
# hardcoding 50/51 was macOS-only and made Linux treat ENETDOWN as fatal).
_TRANSIENT_SEND_ERRNOS = {
    errno.ENETDOWN,
    errno.ENETUNREACH,
    errno.EHOSTUNREACH,
    errno.EADDRNOTAVAIL,
    errno.ENETRESET,
    errno.EHOSTDOWN if hasattr(errno, "EHOSTDOWN") else -1,
}

AF_INET = 2
AF_PACKET = 17  # Linux link-layer (MAC) family in zhelper.get_ifaddrs()
AF_LINK = 18  # BSD/macOS link-layer (MAC) family in zhelper.get_ifaddrs()
# Skip typical container/VM virtual NICs when falling back without a gateway match
_VIRTUAL_IFACE_PREFIXES = (
    "docker",
    "br-",
    "veth",
    "virbr",
    "tun",
    "tap",
    "wg",
    "vnet",
    "vmnet",
    "zt",
    "lxc",
    "cni",
    "flannel",
    "cbr",
)

class ZBeacon(object):

    def __init__(self, ctx, pipe, *args, **kwargs):
        self.ctx = ctx  #  ZMQ context
        self.pipe = pipe  #  Actor command pipe
        self.udpsock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        #  UDP socket for send/recv
        self.port_nbr = 0  #  UDP port number we work on
        self.interval = INTERVAL_DFLT  #  Beacon broadcast interval
        self.ping_at = 0  #  Next broadcast time
        self.transmit = None  #  Beacon transmit data
        self.filter = b""  #  Beacon filter data

        self.terminated = False  #  Did caller ask us to quit?
        self.verbose = False  #  Verbose logging enabled?
        self.hostname = ""  #  Saved host name
        self.udp_ready = False  # True only after successful UDP bind

        self.address = None
        self.mac = None
        self.network_address = None
        self.broadcast_address = None
        self.interface_name = None
        self.run()

    def __del__(self):
        if self.udpsock:
            self.udpsock.close()

    def prepare_udp(self, interface_name=None):
        """
        Resolve interface and bind the UDP socket.

        Returns:
            bool: True if the beacon socket is ready to send/receive.
        """
        self.udp_ready = False
        try:
            self._prepare_socket(interface_name)
        except ValueError:
            logger.exception("Error preparing socket:")
            return False

        if self.broadcast_address is None:
            logger.error("No broadcast address resolved; UDP beacon not ready")
            return False

        try:
            self.udpsock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.udpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            #  On some platforms we have to ask to reuse the port
            try:
                self.udpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

            except AttributeError:
                pass

            if self.broadcast_address.is_multicast:
                # TTL
                self.udpsock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

                # TODO: This should only be used if we do not have inproc method!
                self.udpsock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)

                # Usually, the system administrator specifies the
                # default interface multicast datagrams should be
                # sent from. The programmer can override this and
                # choose a concrete outgoing interface for a given
                # socket with this option.
                #
                # this results in the loopback address?
                # host = socket.gethostbyname(socket.gethostname())
                # self.udpsock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, socket.inet_aton(host))
                # You need to tell the kernel which multicast groups
                # you are interested in. If no process is interested
                # in a group, packets destined to it that arrive to
                # the host are discarded.
                # You can always fill this last member with the
                # wildcard address (INADDR_ANY) and then the kernel
                # will deal with the task of choosing the interface.
                #
                # Maximum memberships: /proc/sys/net/ipv4/igmp_max_memberships
                # self.udpsock.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP,
                #       socket.inet_aton("225.25.25.25") + socket.inet_aton(host))
                self.udpsock.bind(("", self.port_nbr))

                group = socket.inet_aton("{0}".format(self.broadcast_address))
                mreq = struct.pack("4sl", group, socket.INADDR_ANY)

                self.udpsock.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            else:
                # Platform specifics
                if platform.startswith("linux"):
                    # on linux we bind to the broadcast address and send to
                    # the broadcast address
                    self.udpsock.bind((str(self.broadcast_address), self.port_nbr))
                else:
                    self.udpsock.bind(("", self.port_nbr))

                logger.debug(
                    "Set up a broadcast beacon to {0}:{1}".format(
                        self.broadcast_address, self.port_nbr
                    )
                )
        except socket.error:
            logger.exception(
                "Initializing of {0} raised an exception".format(
                    self.__class__.__name__
                )
            )
            return False

        # Loopback-only setup is not usable for LAN discovery
        if str(self.address) == "127.0.0.1":
            logger.warning(
                "Beacon resolved to 127.0.0.1 only; not ready for LAN discovery"
            )
            self.udp_ready = False
            return False

        self.udp_ready = True
        return True

    @staticmethod
    def _is_virtual_iface(name):
        lname = name.lower()
        return any(lname.startswith(prefix) for prefix in _VIRTUAL_IFACE_PREFIXES)

    def __fill_gateways(self, netinf):
        # Default-route interfaces first, then other gateway interfaces.
        default_route_names = []
        other_gateway_names = []
        netifaces_default_interface_names = []
        gateways = netifaces.gateways()
        logger.debug("Gateways: {0}".format(gateways))

        if AF_INET in gateways:
            for address, interface, is_default in gateways[AF_INET]:
                # fix for windows (netifaces.gateway() returns adapter name instead of interface name)
                resolved_names = []
                if platform.startswith("win"):
                    netifaces_default_interface_names.append(interface)
                    for iface in netinf:
                        for name, data in iface.items():
                            if AF_INET in data and data[AF_INET]["adapter"] == interface:
                                resolved_names.append(name)
                else:
                    resolved_names.append(interface)

                target = default_route_names if is_default else other_gateway_names
                for name in resolved_names:
                    if name not in default_route_names and name not in other_gateway_names:
                        target.append(name)

            logger.debug(
                "Default-route interface names '{0}'".format(list(default_route_names))
            )
            logger.debug(
                "Other gateway interface names '{0}'".format(list(other_gateway_names))
            )
            logger.debug(
                "Netifaces default interface names '{0}'".format(
                    list(netifaces_default_interface_names)
                )
            )

        return default_route_names + other_gateway_names, netifaces_default_interface_names

    def __search_mac_addr(self, adapter):
        """
        Search for MAC addr for specified adapter
        Used on windows environnment while data returned by netifaces lib differs from nix envs

        Args:
            adapter (str): adapter name

        Returns:
            str: Found MAC addr or None if nothing found
        """
        try:
            ifaddresses = netifaces.ifaddresses(adapter)
            logger.debug("Ifaddresses result for adapter '%s': %s", adapter, ifaddresses)
            for ifaddress in ifaddresses.values():
                for ifaddress_entry in ifaddress:
                    addr = ifaddress_entry.get("addr")
                    if not addr:
                        continue
                    if re.search("^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", addr):
                        return addr
        except ValueError:
            logger.debug("Error getting data for adapter '%s'", adapter)
        return None

    def _parse_usable_iface(self, name, data):
        """
        Validate an interface and return addressing info, or None if unusable.
        """
        data_2 = data.get(AF_INET)
        if not data_2:
            logger.debug(" - No data_2 found for interface '{0}'.".format(name))
            return None

        logger.debug(" + data_2: %s | %s | %s", data_2, data_2.get(AF_INET), data_2.keys())

        # Linux stores MAC under AF_PACKET (17); macOS/BSD under AF_LINK (18)
        data_mac = data.get(AF_PACKET) or data.get(AF_LINK)
        if not data_mac and platform.startswith("win") and data_2.get("adapter"):
            # last chance to get mac address on windows platform
            adapter = data_2.get("adapter")
            mac_addr = self.__search_mac_addr(adapter)
            if mac_addr:
                data_mac = {"addr": mac_addr}
        if not data_mac:
            logger.debug(
                " - No MAC (AF_PACKET/AF_LINK) found for interface '{0}'.".format(name)
            )
            return None

        address_str = data_2.get("addr")
        netmask_str = data_2.get("netmask")
        mac_str = data_mac.get("addr")

        if not address_str or not netmask_str:
            logger.debug(
                " - Address or netmask not found for interface '{0}'.".format(name)
            )
            return None

        if isinstance(address_str, bytes):
            address_str = address_str.decode("utf8")

        if isinstance(netmask_str, bytes):
            netmask_str = netmask_str.decode("utf8")

        if isinstance(mac_str, bytes):
            mac_str = mac_str.decode("utf8")

        # keep only private interface
        ip_address = netaddr.IPAddress(address_str)
        # handle netaddr breaking changes
        if netaddr.__version__.startswith("0."):
            # is_private does not exist anymore on new IpAddress lib version
            # pylint: disable=no-member
            ip_is_private = ip_address.is_private()
        else:
            ip_is_private = (
                ip_address.is_ipv4_private_use()
                or ip_address.is_ipv6_unique_local()
            )
        if ip_address and not ip_is_private:
            logger.debug(
                " - Interface '{0}' refers to public ip address, drop it.".format(name)
            )
            return None

        interface_string = "{0}/{1}".format(address_str, netmask_str)
        interface = ipaddress.ip_interface(interface_string)
        if interface.is_loopback:
            logger.debug(" - Interface {0} is a loopback device.".format(name))
            return None

        if interface.is_link_local:
            logger.debug(" - Interface {0} is a link-local device.".format(name))
            return None

        return {
            "address": ip_address,
            "mac": mac_str,
            "network_address": interface.network.network_address,
            "broadcast_address": interface.network.broadcast_address,
            "interface_name": name,
        }

    def _prepare_socket(self, interface_name=None):
        netinf = zhelper.get_ifaddrs()
        logger.debug("Available interfaces: {0}".format(netinf))

        # Prefer default-route / gateway interfaces, then any private LAN NIC.
        (gateway_interface_names, _netifaces_names) = self.__fill_gateways(netinf)

        gateway_candidates = []
        other_candidates = []

        for iface in netinf:
            # ipv4 only currently and needs a valid broadcast address
            for name, data in iface.items():
                logger.debug("------------------")
                logger.debug("Checking interface '{0}'".format(name))
                logger.debug("Data: %s", data)
                if interface_name and interface_name != name:
                    logger.debug(
                        " - Interface '{0}' is not specified one '{1}'".format(
                            name, interface_name
                        )
                    )
                    continue

                # Auto-selection skips virtual NICs; explicit interface_name wins
                if not interface_name and self._is_virtual_iface(name):
                    logger.debug(
                        " - Interface '{0}' looks virtual, skip for beacon".format(name)
                    )
                    continue

                info = self._parse_usable_iface(name, data)
                if not info:
                    continue

                if name in gateway_interface_names:
                    priority = gateway_interface_names.index(name)
                    gateway_candidates.append((priority, info))
                else:
                    other_candidates.append(info)

        logger.debug("Finished scanning interfaces.")

        selected = None
        if gateway_candidates:
            gateway_candidates.sort(key=lambda item: item[0])
            selected = gateway_candidates[0][1]
            logger.debug(
                "Selected gateway interface '{0}'".format(selected["interface_name"])
            )
        elif other_candidates:
            # No gateway match yet (boot / flap): use first private LAN iface
            selected = other_candidates[0]
            logger.warning(
                "No default-route interface for beacon; using '%s' (%s)",
                selected["interface_name"],
                selected["address"],
            )

        if selected:
            self.address = selected["address"]
            self.mac = selected["mac"]
            self.network_address = selected["network_address"]
            self.broadcast_address = selected["broadcast_address"]
            self.interface_name = selected["interface_name"]
        else:
            # Last resort: loopback + multicast. Upper layers should treat
            # 127.0.0.1 as "not ready for LAN discovery" and retry.
            logger.warning(
                "No usable LAN interface found for ZRE beacon; falling back to "
                "127.0.0.1 (discovery will not work on the LAN until a network "
                "is available)"
            )
            self.network_address = ipaddress.IPv4Address(u("127.0.0.1"))
            self.broadcast_address = ipaddress.IPv4Address(u(MULTICAST_GRP))
            self.interface_name = "loopback"
            self.address = u("127.0.0.1")
            self.mac = None

        logger.debug("Address: {0}".format(self.address))
        logger.debug("MAC: {0}".format(self.mac))
        logger.debug("Network: {0}".format(self.network_address))
        logger.debug("Broadcast: {0}".format(self.broadcast_address))
        logger.debug("Choosen interface name: {0}".format(self.interface_name))

    def configure(self, interface_name, port_nbr):
        self.port_nbr = port_nbr
        ok = self.prepare_udp(interface_name)
        if not ok:
            logger.error(
                "UDP beacon setup failed on %s; terminating beacon actor",
                self.address,
            )
            # Force an unusable address so PyreNode aborts start cleanly
            # instead of half-running with a dead UDP socket.
            self.address = u("127.0.0.1")
            self.terminated = True
        # Always answer CONFIGURE so the node API does not block.
        self.pipe.send_unicode(
            str(self.address) if self.address is not None else "127.0.0.1"
        )

    def handle_pipe(self):
        #  Get just the commands off the pipe
        request = self.pipe.recv_multipart()
        command = request.pop(0).decode("UTF-8")
        if not command:
            return -1  #  Interrupted

        if self.verbose:
            logger.debug("zbeacon: API command={0}".format(command))

        if command == "VERBOSE":
            self.verbose = True
        elif command == "CONFIGURE":
            # unpacking code from https://bit.ly/2qN3ZUz
            interface_data = request.pop(0)

            (interface_name_len,), interface = (
                struct.unpack("I", interface_data[:4]),
                interface_data[4:],
            )
            interface = interface.decode("UTF-8")

            port = struct.unpack("I", request.pop(0))[0]
            self.configure(interface, port)
        elif command == "PUBLISH":
            self.transmit = request.pop(0)
            if self.interval == 0:
                self.interval = INTERVAL_DFLT
            # Start broadcasting immediately
            self.ping_at = time.time()
        elif command == "SILENCE":
            self.transmit = None
        elif command == "SUBSCRIBE":
            self.filter = request.pop(0)
        elif command == "UNSUBSCRIBE":
            self.filter = None
        elif command == "$TERM":
            self.terminated = True
        else:
            logger.error("zbeacon: - invalid command: {0}".format(command))

    def handle_udp(self):
        if not self.udp_ready:
            return
        try:
            frame, addr = self.udpsock.recvfrom(BEACON_MAX)

        except Exception as e:
            logger.exception("Exception while receiving: {0}".format(e))
            return

        peername = addr[0]

        #  If filter is set, check that beacon matches it
        is_valid = False
        if self.filter is not None:
            if len(self.filter) <= len(frame):
                match_data = frame[: len(self.filter)]
                if match_data == self.filter:
                    is_valid = True

        #  If valid, discard our own broadcasts, which UDP echoes to us
        if is_valid and self.transmit:
            if frame == self.transmit:
                is_valid = False

        #  If still a valid beacon, send on to the API
        if is_valid:
            self.pipe.send_unicode(peername, zmq.SNDMORE)
            self.pipe.send(frame)

    def send_beacon(self):
        if not self.udp_ready or not self.transmit:
            return
        try:
            self.udpsock.sendto(
                self.transmit, (str(self.broadcast_address), self.port_nbr)
            )

        except OSError as e:
            # Network may be temporarily down or interface may be changing.
            # Keep the beacon actor alive and retry on the next interval —
            # terminating here leaves upper layers with a silent "zombie" node
            # that no longer advertises on the LAN.
            if e.errno in _TRANSIENT_SEND_ERRNOS:
                logger.warning(
                    "Beacon send deferred (transient errno=%s): %s", e.errno, e
                )
            else:
                logger.warning(
                    "Beacon send failed (errno=%s), keeping beacon alive: %s",
                    e.errno,
                    e,
                )

        except socket.error as e:
            logger.warning("Beacon send failed, keeping beacon alive: %s", e)

    def run(self):
        # Signal actor successfully initialized
        self.pipe.signal()

        self.poller = zmq.Poller()
        self.poller.register(self.pipe, zmq.POLLIN)
        self.poller.register(self.udpsock, zmq.POLLIN)

        while not self.terminated:
            timeout = 1
            if self.transmit and self.udp_ready:
                timeout = self.ping_at - time.time()
                if timeout < 0:
                    timeout = 0
            # Poll on API pipe and on UDP socket
            items = dict(self.poller.poll(timeout * 1000))
            if self.pipe in items and items[self.pipe] == zmq.POLLIN:
                self.handle_pipe()
            if (
                self.udp_ready
                and self.udpsock.fileno() in items
                and items[self.udpsock.fileno()] == zmq.POLLIN
            ):
                self.handle_udp()

            if self.transmit and self.udp_ready and time.time() >= self.ping_at:
                self.send_beacon()
                self.ping_at = time.time() + self.interval


if __name__ == "__main__":
    import zmq
    import struct
    import time

    speaker = ZActor(zmq.Context(), ZBeacon)
    speaker.send_unicode("VERBOSE")
    speaker.send_unicode("CONFIGURE", zmq.SNDMORE)
    speaker.send(struct.pack("I", 9999))
    speaker.send_unicode("PUBLISH", zmq.SNDMORE)
    import uuid

    transmit = struct.pack(
        "cccb16sH", b"Z", b"R", b"E", 1, uuid.uuid4().bytes, socket.htons(1300)
    )
    speaker.send(transmit)
    speaker.destroy()

