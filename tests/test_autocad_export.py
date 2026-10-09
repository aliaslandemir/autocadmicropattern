import unittest
from unittest.mock import MagicMock, patch

import autocad_export as export
from geometry import PatternParameters


class BusyError(Exception):
    hresult = -2147418111


class AutoCADTests(unittest.TestCase):
    def test_retries_server_busy_calls(self):
        operation = MagicMock(side_effect=[BusyError(), BusyError(), "ok"])
        with patch("autocad_bridge.time.sleep") as sleep:
            self.assertEqual(export.retry_com(operation), "ok")
        self.assertEqual(operation.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_does_not_retry_other_errors(self):
        operation = MagicMock(side_effect=ValueError("invalid geometry"))
        with self.assertRaises(ValueError):
            export.retry_com(operation)
        self.assertEqual(operation.call_count, 1)

    def test_retry_exhaustion_preserves_error(self):
        operation = MagicMock(side_effect=BusyError("busy"))
        with patch("autocad_bridge.time.sleep"), self.assertRaises(BusyError):
            export.retry_com(operation)
        self.assertEqual(operation.call_count, 3)

    def test_lazy_connection_is_actually_attempted(self):
        first = MagicMock()
        type(first).model = property(lambda self: (_ for _ in ()).throw(BusyError()))
        second = MagicMock()
        with patch.object(export, "PYAUTOCAD_AVAILABLE", True), patch.object(export, "Autocad", side_effect=[first, second]), patch("autocad_bridge.time.sleep"):
            self.assertIs(export.get_autocad_instance(), second)

    def run_transfer(self, params, acad=None, **kwargs):
        acad = acad or MagicMock()
        com = MagicMock()
        with patch.object(export, "PYAUTOCAD_AVAILABLE", True), patch.object(export, "pythoncom", com), patch.object(export, "APoint", lambda *v: tuple(v)), patch.object(export, "get_autocad_instance", return_value=acad):
            try:
                export.transfer_to_autocad(params, **kwargs)
            finally:
                com.CoInitialize.assert_called_once()
                com.CoUninitialize.assert_called_once()
        return acad

    def test_rectangle_and_ring_counts(self):
        progress = MagicMock()
        acad = self.run_transfer(PatternParameters(radius=1), progress=progress)
        self.assertEqual(acad.model.AddLine.call_count, 7*4)
        acad.model.AddCircle.assert_called_once_with((0, 0), 45)
        acad.doc.StartUndoMark.assert_called_once()
        acad.doc.EndUndoMark.assert_called_once()
        progress.assert_called_once_with(7, 7)

    def test_triangle_and_disabled_rings(self):
        acad = self.run_transfer(PatternParameters(radius=0, shape_type="triangle", circle_r=0, circle_r2=0))
        self.assertEqual(acad.model.AddLine.call_count, 3)
        acad.model.AddCircle.assert_not_called()

    def test_circle_export(self):
        acad = self.run_transfer(PatternParameters(radius=0, shape_type="circle", circle_r=0, circle_r2=0))
        acad.model.AddLine.assert_not_called()
        acad.model.AddCircle.assert_called_once_with((0, 0), 10)

    def test_cancellation_balances_com_and_undo_group(self):
        acad = MagicMock()
        with self.assertRaises(export.TransferCancelled):
            self.run_transfer(PatternParameters(), acad, cancelled=lambda: True)
        acad.doc.EndUndoMark.assert_called_once()
        acad.model.AddLine.assert_not_called()

    def test_failed_entity_balances_com_and_undo_group(self):
        acad = MagicMock()
        acad.model.AddLine.side_effect = ValueError("drawing error")
        with self.assertRaisesRegex(ValueError, "drawing error"):
            self.run_transfer(PatternParameters(), acad)
        acad.doc.EndUndoMark.assert_called_once()

    def test_cleanup_error_does_not_hide_drawing_error(self):
        acad = MagicMock()
        acad.model.AddLine.side_effect = ValueError("drawing error")
        acad.doc.EndUndoMark.side_effect = RuntimeError("cleanup error")
        with self.assertRaisesRegex(ValueError, "drawing error"):
            self.run_transfer(PatternParameters(), acad)

    def test_connection_failure_balances_com(self):
        com = MagicMock()
        with patch.object(export, "PYAUTOCAD_AVAILABLE", True), patch.object(export, "pythoncom", com), patch.object(export, "get_autocad_instance", side_effect=RuntimeError("connection failed")):
            with self.assertRaisesRegex(RuntimeError, "connection failed"):
                export.transfer_to_autocad(PatternParameters())
        com.CoUninitialize.assert_called_once()

    def test_unavailable_integration_has_clear_error(self):
        with patch.object(export, "PYAUTOCAD_AVAILABLE", False), patch.object(export, "WSL_AVAILABLE", False), self.assertRaisesRegex(RuntimeError, "Windows Python"):
            export.transfer_to_autocad(PatternParameters())


if __name__ == "__main__":
    unittest.main()
