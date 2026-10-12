#!/bin/sh
# Run each test module in its own process (gevent/zmq.green leave process-global
# state that can segfault a single long unittest discover run).
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

# Unit tests first, then integration (pyre last can be flaky under gevent/zmq.green).
MODULES="
tests.test_zbeacon_send
tests.test_zbeacon_iface
tests.test_pyre_peer_seq
tests.test_zactor_is_zactor
tests.test_zhelper
tests.test_zactor
tests.test_pyre
tests.test_zbeacon
"

failed=0
for mod in $MODULES; do
    echo "======== $mod ========"
    if ! python -m unittest "$mod" -v; then
        failed=1
    fi
done

# Not run in CI: tests.test_network_disconnect (needs nmcli + DEVICE env)

if [ "$failed" -ne 0 ]; then
    echo "One or more test modules failed"
    exit 1
fi
echo "All test modules passed"
