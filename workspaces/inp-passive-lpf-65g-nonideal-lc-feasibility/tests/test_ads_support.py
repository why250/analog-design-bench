"""Offline safety checks for switching ADS workspaces after normalization."""
import importlib.util
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

try:
    from ._bootstrap import TOOLS
except ImportError:
    from _bootstrap import TOOLS


def support_with_workspace(path, *, modified):
    """Load only the small support module against an offline ADS API double."""
    keysight = ModuleType("keysight")
    ads = ModuleType("keysight.ads")
    de = ModuleType("keysight.ads.de")
    db = ModuleType("keysight.ads.de.db_uu")
    app = ModuleType("keysight.ads.de.app")
    current = SimpleNamespace(path=path)
    de.workspace_is_open = lambda: True
    de.active_workspace = lambda: current
    de.is_pde_app = lambda: True
    de.close_workspace = Mock()
    de.open_workspace = Mock()
    de.create_workspace = Mock()
    app.WindowType = SimpleNamespace(SCHEMATIC_WINDOW="schematic",
                                    SYMBOL_WINDOW="symbol", LAYOUT_WINDOW="layout")
    app.find_windows_by_type = lambda kind: ["existing-window"] if kind == "schematic" else []
    app.get_design_in_uu_from_window = lambda window: "existing-design"
    ads.ael = SimpleNamespace(call=SimpleNamespace(db_design_is_modified=lambda design: modified))
    ads.de = de
    de.db_uu = db
    de.app = app
    modules = {"keysight": keysight, "keysight.ads": ads, "keysight.ads.de": de,
               "keysight.ads.de.db_uu": db, "keysight.ads.de.app": app}
    spec = importlib.util.spec_from_file_location("task_ads_support_safety", TOOLS/"ads_support.py")
    support = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", modules):
        spec.loader.exec_module(support)
    return support, de, current, modules


class WorkspaceSafetyTests(unittest.TestCase):
    def test_modified_native_design_blocks_switch_and_directory_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder)/"original_wrk"
            new = Path(folder)/"new-task"/"candidate_wrk"
            support, de, _, modules = support_with_workspace(old, modified=True)
            with patch.dict("sys.modules", modules), self.assertRaisesRegex(RuntimeError, "Save existing modified designs"):
                support._switch_workspace(new)
            de.close_workspace.assert_not_called()
            de.open_workspace.assert_not_called()
            de.create_workspace.assert_not_called()
            self.assertFalse(new.parent.exists())

    def test_reusing_same_workspace_keeps_existing_design_session(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/"existing_wrk"
            support, de, current, modules = support_with_workspace(target, modified=True)
            with patch.dict("sys.modules", modules):
                self.assertIs(support._switch_workspace(target), current)
            de.close_workspace.assert_not_called()
            de.open_workspace.assert_not_called()
            de.create_workspace.assert_not_called()


if __name__ == "__main__":
    unittest.main()
