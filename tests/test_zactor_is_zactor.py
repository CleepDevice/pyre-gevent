"""Unit test for ZActor.is_zactor isinstance check."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("zmq", MagicMock())
sys.modules.setdefault("zmq.green", MagicMock())

# Stub package modules imported by zactor
_pkg = type(sys)("pyre_gevent")
_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "pyre_gevent")]
sys.modules.setdefault("pyre_gevent", _pkg)
sys.modules.setdefault("pyre_gevent.zsocket", MagicMock())
sys.modules.setdefault("pyre_gevent.zhelper", MagicMock())

_zactor_path = Path(__file__).resolve().parents[1] / "pyre_gevent" / "zactor.py"
_spec = importlib.util.spec_from_file_location("pyre_gevent.zactor", _zactor_path)
_zactor_mod = importlib.util.module_from_spec(_spec)
sys.modules["pyre_gevent.zactor"] = _zactor_mod
_spec.loader.exec_module(_zactor_mod)
ZActor = _zactor_mod.ZActor


class ZActorIsZactorTest(unittest.TestCase):
    def test_is_zactor_true_for_instance(self):
        actor = ZActor.__new__(ZActor)
        self.assertTrue(actor.is_zactor())
        self.assertFalse(ZActor.is_zactor(object()))


if __name__ == "__main__":
    unittest.main()
