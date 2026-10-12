#!/bin/sh
# Optional local integration tests (real UDP beacon / two Pyre nodes).
# NOT used by CI: gevent/zmq.green teardown can SIGSEGV intermittently.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

MODULES="
tests.test_pyre
tests.test_zbeacon
"

# Needs nmcli + DEVICE=… : tests.test_network_disconnect

failed=0
for mod in $MODULES; do
    echo "======== $mod ========"
    if ! python -m unittest "$mod" -v; then
        failed=1
    fi
done

if [ "$failed" -ne 0 ]; then
    echo "One or more integration test modules failed"
    exit 1
fi
echo "All integration test modules passed"
