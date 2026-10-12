# Changelog

## [1.0.0] - 2026-10-12

First stable release (out of 0.x). Hardens ZRE discovery for long-running Cleep
devices and modernizes packaging / CI.

### Fixed
- Keep the UDP beacon alive on transient send errors (`ENETDOWN`, `ENETUNREACH`,
  etc.) instead of suiciding the actor and emitting `$TERM` (LAN peers going
  invisible after long uptime / network flaps)
- Do not send on an unbound UDP socket when `prepare_udp` fails (`udp_ready`)
- Prefer a real private interface over silent loopback when selecting the beacon iface
- Fix interface / MAC selection edge cases, including macOS link-layer (`AF_LINK`)
- Fix peer sequence handling and `ZActor` identity checks that could corrupt
  discovery state
- Declare runtime dependencies properly (`gevent`, `pyzmq`, `netaddr`,
  `netifaces-plus`) with floors compatible with Cleep/Bullseye prebuild wheels

### Changed
- Require Python `>=3.9`
- Raise dependency floors: `gevent>=22.10.2`, `pyzmq>=22.3.0`, `netaddr>=1.0.0`,
  `netifaces-plus>=0.12.0`
- Publish to PyPI via GitHub Actions on `v*` tags (replace Travis + local
  publish scripts); unit tests must pass before upload
- Drop netaddr 0.x compatibility branch (require 1.x private-IP API only)
- Remove deprecated / unimplemented public API: `get_peer_name`, `set_name`,
  `set_endpoint`, gossip stubs; drop obsolete Vagrant + Sphinx docs (README is
  the doc of record)

### Added
- Unit tests for beacon send resilience and interface selection
- `scripts/run_tests.sh` (stable unit tests, per-module processes) as publish CI gate;
  integration ZRE/UDP tests moved to optional `run_tests_integration.sh` (flaky under
  gevent teardown, not run in CI)
- Robust `Pyre.set_interface(name)` (before `start`): forces the UDP beacon NIC
  via `SET INTERFACE`, aligned with zeromq/pyre; no silent fallback to another
  iface when the forced name is missing/unusable
