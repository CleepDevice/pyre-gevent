#!/bin/sh
# CI gate: stable unit tests only (one process per module).
# Integration tests (real ZRE / UDP) live in run_tests_integration.sh — they can
# SIGSEGV under gevent/zmq.green teardown and must not block publish.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

MODULES="
tests.test_zbeacon_send
tests.test_zbeacon_iface
tests.test_pyre_peer_seq
tests.test_zactor_is_zactor
tests.test_zhelper
tests.test_zactor
"

failed=0
for mod in $MODULES; do
    echo "======== $mod ========"
    if ! python -m unittest "$mod" -v; then
        failed=1
    fi
done

if [ "$failed" -ne 0 ]; then
    echo "One or more unit test modules failed"
    exit 1
fi
echo "All unit test modules passed"
