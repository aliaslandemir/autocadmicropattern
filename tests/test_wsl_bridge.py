"""Exercise the bridge pipes with real child processes, without AutoCAD."""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

import autocad_export as export
from geometry import PatternParameters


class WSLBridgeTests(unittest.TestCase):
    def test_actual_helper_with_fake_windows_com(self):
        source = export.Path(export.__file__).with_name("autocad_bridge.py").read_text()
        fake_windows = '''import sys, types
sys.platform = "win32"
state = {"lines": 0, "circles": 0, "undo": False, "initialized": False}
def initialize():
    state["initialized"] = True
def uninitialize():
    assert state == {"lines": 4, "circles": 1, "undo": False, "initialized": True}, state
def start():
    state["undo"] = True
def end():
    state["undo"] = False
def line(*args):
    state["lines"] += 1
def circle(*args):
    state["circles"] += 1
acad = types.SimpleNamespace(model=types.SimpleNamespace(AddLine=line, AddCircle=circle),
                             doc=types.SimpleNamespace(StartUndoMark=start, EndUndoMark=end))
sys.modules["pythoncom"] = types.SimpleNamespace(CoInitialize=initialize, CoUninitialize=uninitialize)
sys.modules["pyautocad"] = types.SimpleNamespace(Autocad=lambda **kwargs: acad, APoint=lambda *v: v)
'''
        progress = MagicMock()
        self.run_bridge(fake_windows + source, progress=progress)
        progress.assert_called_once_with(1, 1)

    def run_bridge(self, source, **kwargs):
        with patch.object(export, "windows_python_command", return_value=[sys.executable]), \
                patch.object(export.Path, "read_text", return_value=source):
            return export.transfer_via_windows(export.geometry_payload(PatternParameters(radius=0)), **kwargs)

    def test_wsl_routes_validated_geometry_without_local_com(self):
        with patch.object(export, "PYAUTOCAD_AVAILABLE", False), \
                patch.object(export, "WSL_AVAILABLE", True), \
                patch.object(export, "transfer_via_windows") as bridge:
            export.transfer_to_autocad(PatternParameters(radius=0, shape_type="triangle"))
        geometry = bridge.call_args.args[0]
        self.assertEqual(len(geometry["shapes"]), 1)
        self.assertEqual(len(geometry["shapes"][0]), 3)
        self.assertEqual(geometry["center_circle_radii"], (45,))

    def test_invalid_parameters_never_launch_bridge(self):
        with patch.object(export, "transfer_via_windows") as bridge:
            with self.assertRaises(ValueError):
                export.transfer_to_autocad(PatternParameters(radius=-1))
        bridge.assert_not_called()

    def test_progress_success_and_json_geometry(self):
        progress = MagicMock()
        self.run_bridge('''import json, sys
geometry = json.loads(sys.stdin.readline())
assert len(geometry["shapes"]) == 1
assert len(geometry["shapes"][0]) == 4
print("third-party diagnostic", flush=True)
print('AUTOCAD_BRIDGE {"event":"progress","done":1,"total":1}', flush=True)
print('AUTOCAD_BRIDGE {"event":"success"}', flush=True)
''', progress=progress)
        progress.assert_called_once_with(1, 1)

    def test_child_error_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, "missing dependencies"):
            self.run_bridge('''print('AUTOCAD_BRIDGE {"event":"error","message":"missing dependencies"}')
raise SystemExit(1)
''')

    def test_unexpected_exit_includes_diagnostics(self):
        with self.assertRaisesRegex(RuntimeError, "interpreter failed"):
            self.run_bridge('print("interpreter failed")\nraise SystemExit(3)')

    def test_cooperative_cancellation_reaches_child(self):
        stopped = False

        def progress(done, total):
            nonlocal stopped
            stopped = True

        with self.assertRaisesRegex(export.TransferCancelled, "cancelled"):
            self.run_bridge('''import sys
sys.stdin.readline()
print('AUTOCAD_BRIDGE {"event":"progress","done":25,"total":100}', flush=True)
assert sys.stdin.readline().strip() == "cancel"
print('AUTOCAD_BRIDGE {"event":"cancelled","message":"Transfer cancelled"}', flush=True)
raise SystemExit(2)
''', progress=progress, cancelled=lambda: stopped)

    def test_cancel_before_launch(self):
        with patch.object(export.subprocess, "Popen") as launch, \
                self.assertRaises(export.TransferCancelled):
            export.transfer_via_windows({}, cancelled=lambda: True)
        launch.assert_not_called()

    def test_explicit_interpreter_with_spaces_is_one_argument(self):
        with patch.dict(os.environ, AUTOCAD_WINDOWS_PYTHON="/mnt/c/Program Files/Python/python.exe"):
            self.assertEqual(export.windows_python_command(), ["/mnt/c/Program Files/Python/python.exe"])

    def test_windows_path_is_converted(self):
        with patch.dict(os.environ, AUTOCAD_WINDOWS_PYTHON=r"C:\Python\python.exe"), \
                patch.object(export.subprocess, "run", return_value=MagicMock(stdout="/mnt/c/Python/python.exe\n")) as run:
            self.assertEqual(export.windows_python_command(), ["/mnt/c/Python/python.exe"])
        self.assertEqual(run.call_args.args[0], ["wslpath", "-u", r"C:\Python\python.exe"])

    def test_plain_linux_is_preview_only(self):
        with patch.object(export.sys, "platform", "linux"), patch.dict(os.environ, {}, clear=True), \
                patch.object(export.Path, "read_text", return_value="6.8.0-generic"):
            self.assertFalse(export.is_wsl())


if __name__ == "__main__":
    unittest.main()
