"""Unit tests for PyrePeer sequence tracking."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock

sys.modules.setdefault("zmq", MagicMock())
sys.modules.setdefault("zmq.green", MagicMock())

# Load module file directly to avoid package __init__ (pyzmq/netaddr deps)
_peer_path = Path(__file__).resolve().parents[1] / "pyre_gevent" / "pyre_peer.py"
_spec = importlib.util.spec_from_file_location("pyre_peer", _peer_path)
_peer_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_peer_mod)
PyrePeer = _peer_mod.PyrePeer


class FakeMsg(object):
    def __init__(self, command, sequence):
        self._command = command
        self._sequence = sequence

    def get_command(self):
        return self._command

    def get_sequence(self):
        return self._sequence


class PyrePeerSeqTest(unittest.TestCase):
    def test_hello_resets_sequence(self):
        peer = PyrePeer(Mock(), Mock())
        peer.want_sequence = 42

        lost = peer.messages_lost(FakeMsg("HELLO", 1))

        self.assertFalse(lost)
        self.assertEqual(peer.want_sequence, 1)

    def test_non_hello_increments_sequence(self):
        peer = PyrePeer(Mock(), Mock())
        peer.want_sequence = 1

        lost = peer.messages_lost(FakeMsg("WHISPER", 2))

        self.assertFalse(lost)
        self.assertEqual(peer.want_sequence, 2)

    def test_sequence_mismatch_reports_lost(self):
        peer = PyrePeer(Mock(), Mock())
        peer.want_sequence = 1

        lost = peer.messages_lost(FakeMsg("WHISPER", 99))

        self.assertTrue(lost)


if __name__ == "__main__":
    unittest.main()
