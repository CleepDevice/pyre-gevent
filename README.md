# pyre-gevent

Python [ZRE](http://rfc.zeromq.org/spec:36) / [Zyre](http://zyre.org) stack for
**gevent**, based on [zeromq/pyre](https://github.com/zeromq/pyre).

Used by Cleep (`cleepapp-cleepbus`) for LAN device discovery and messaging.

```sh
pip install pyre-gevent
```

## Concepts

| Piece | Role |
|-------|------|
| **UDP beacon** (`ZBeacon`) | Broadcasts presence on the LAN (default port **5670**) |
| **TCP inbox** | Peers connect after discovery; whispers / shouts go here |
| **Groups** | Named multicast channels (`join` / `shout`) |
| **Headers** | Key/value metadata exchanged on `ENTER` |

**Interface selection**

- Default: pick a private LAN iface (default-route / gateway first). Virtual
  NICs (`docker0`, `veth*`, …) are skipped unless forced.
- Optional: `node.set_interface("eth0")` **before** `start()` forces that NIC.
  If it is missing or unusable, discovery fails cleanly (no silent fallback).

**Resilience (this fork)**

- Transient UDP send errors (`ENETDOWN`, …) do **not** kill the beacon.
- Beacon only sends when the UDP socket is ready (`udp_ready`).
- Apps (e.g. cleepbus) can restart discovery on `$TERM` / network events.

**Not implemented:** Zyre gossip / `SET ENDPOINT` (UDP beacon mode only).

## Quick API

```python
from pyre_gevent import Pyre

node = Pyre("my-node")
node.set_header("role", "device")
# node.set_interface("eth0")   # optional, before start
node.start()
node.join("CLEEP")

# events: ENTER / EXIT / JOIN / LEAVE / WHISPER / SHOUT
frames = node.recv()

node.whisper(peer_uuid, b"hello")
node.shout("CLEEP", b"hello all")
node.stop()
```

Import package name: `pyre_gevent` (PyPI: `pyre-gevent`).

See `examples/chat.py` for a fuller chat sample.

## Requirements

Python **≥ 3.9**. Declared in `setup.py`:

- `gevent >= 22.10.2`
- `pyzmq >= 22.3.0`
- `netaddr >= 1.0.0`
- `netifaces-plus >= 0.12.0`

## Tests

```sh
pip install .
sh scripts/run_tests.sh              # CI gate — stable unit tests only
# sh scripts/run_tests_integration.sh  # optional local: real ZRE/UDP (can SIGSEGV)
```

CI never runs the integration suite: `gevent` / `zmq.green` teardown can
segfault under rapid create/destroy, which would make publish flaky.

## Release

1. Bump `version` in `setup.py` and `pyre_gevent/__init__.py`.
2. Update `CHANGELOG.md`.
3. `git tag vX.Y.Z && git push origin vX.Y.Z`
4. GitHub Actions runs tests, then uploads to PyPI.

Needs repo environment **`actions`** with secret **`PYPI_API_TOKEN`**.

## License

LGPLv3 — see `LICENSE` / `AUTHORS`. Upstream issues:
[zeromq/pyre](https://github.com/zeromq/pyre/issues).
