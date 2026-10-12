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
  publish scripts)

### Added
- Unit tests for beacon send resilience and interface selection
