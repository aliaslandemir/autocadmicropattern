import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import threading
import time

from PyQt5.QtWidgets import QApplication

from GUI import AdvancedHexGUI
from geometry import PatternParameters


class GUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.gui = AdvancedHexGUI()

    def tearDown(self):
        self.gui.close()
        self.gui.deleteLater()
        self.app.processEvents()

    def test_default_preview_is_generated(self):
        self.assertEqual(self.gui.preview_parameters, PatternParameters(defect2=(0, 0), triangle_edge=1, shape_circle_r=1))
        self.assertTrue(self.gui.save_button.isEnabled())
        self.assertEqual(len(self.gui.canvas.ax.patches), 1)
        self.assertEqual(len(self.gui.canvas.ax.texts), 271)

    def test_inactive_inputs_do_not_block_generation(self):
        self.gui.rect_w_input.setText("bad")
        self.gui.rect_h_input.setText("")
        self.gui.def2_input.setText("bad")
        self.gui.shape_combo.setCurrentText("Triangle")
        self.gui.on_generate()
        self.assertEqual(self.gui.preview_parameters.shape_type, "triangle")

    def test_two_defects_ignore_inactive_multiplier(self):
        self.gui.two_defects_radio.click()
        self.gui.m_input.setText("bad")
        self.assertFalse(self.gui.m_input.isEnabled())
        self.assertEqual(self.gui.get_parameters().one_or_two, 2)

    def test_nonfinite_coordinates_and_dimensions_are_rejected(self):
        for widget, invalid in ((self.gui.side_len_input, "nan"), (self.gui.def1_input, "inf,0"),
                                (self.gui.circle_r_input, "-1")):
            with self.subTest(value=invalid):
                previous = widget.text()
                widget.setText(invalid)
                self.assertIsNone(self.gui.get_parameters())
                widget.setText(previous)

    def test_all_shapes_render_and_fit_in_axes(self):
        for shape in ("rectangle", "triangle", "circle"):
            params = replace(PatternParameters(), radius=0, shape_type=shape,
                             rect_w=1000, rect_h=500, triangle_edge=1000,
                             shape_circle_r=1000, circle_r=2000, circle_r2=0,
                             defect1=(3000, 0))
            self.gui.canvas.draw_hex_grid(params)
            xlim, ylim = self.gui.canvas.ax.get_xlim(), self.gui.canvas.ax.get_ylim()
            self.assertLess(xlim[0], -2000)
            self.assertGreater(xlim[1], 3000)
            self.assertLess(ylim[0], -2000)
            self.assertGreater(ylim[1], 2000)

    def test_large_grid_uses_collections_and_omits_labels(self):
        self.gui.canvas.draw_hex_grid(replace(PatternParameters(), radius=13))
        self.assertEqual(len(self.gui.canvas.ax.texts), 0)
        self.assertEqual(len(self.gui.canvas.ax.collections), 4)

    def test_zero_rings_and_hidden_grid(self):
        params = replace(PatternParameters(), circle_r=0, circle_r2=0)
        self.gui.canvas.draw_hex_grid(params, show_grid=False, show_angles=False)
        self.assertEqual(len(self.gui.canvas.ax.patches), 0)
        self.assertEqual(len(self.gui.canvas.ax.texts), 0)
        self.assertEqual(len(self.gui.canvas.ax.collections), 3)

    def wait_for_worker(self):
        deadline = time.monotonic() + 5
        while self.gui.transfer_worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertIsNone(self.gui.transfer_worker, "Transfer worker did not finish")

    def test_transfer_runs_off_ui_thread_and_restores_controls(self):
        ui_thread = threading.get_ident()
        worker_threads = []
        def transfer(params, progress, cancelled):
            worker_threads.append(threading.get_ident())
            progress(1, 1)
        with patch("GUI.AUTOCAD_AVAILABLE", True), patch("GUI.transfer_to_autocad", side_effect=transfer):
            self.gui.on_transfer()
            self.assertFalse(self.gui.transfer_button.isEnabled())
            self.wait_for_worker()
            self.assertNotEqual(worker_threads, [ui_thread])
            self.assertEqual(len(worker_threads), 1)
            self.assertTrue(self.gui.transfer_button.isEnabled())
            self.assertFalse(self.gui.cancel_button.isEnabled())
            self.assertIn("Transfer to AutoCAD complete", self.gui.log_area.toPlainText())

    def test_transfer_failure_is_reported_and_controls_restored(self):
        with patch("GUI.AUTOCAD_AVAILABLE", True), patch("GUI.transfer_to_autocad", side_effect=RuntimeError("test failure")):
            self.gui.on_transfer()
            self.wait_for_worker()
            self.assertTrue(self.gui.transfer_button.isEnabled())
            self.assertIn("test failure", self.gui.log_area.toPlainText())
            self.assertIn("Partial geometry", self.gui.log_area.toPlainText())

    def test_close_requests_cancellation_without_destroying_worker(self):
        def transfer(params, progress, cancelled):
            deadline = time.monotonic() + 3
            while not cancelled() and time.monotonic() < deadline:
                time.sleep(0.01)
        with patch("GUI.AUTOCAD_AVAILABLE", True), patch("GUI.transfer_to_autocad", side_effect=transfer):
            self.gui.on_transfer()
            self.assertFalse(self.gui.close())
            self.assertTrue(self.gui.transfer_worker.isInterruptionRequested())
            self.wait_for_worker()
            self.assertTrue(self.gui.close())

    def test_save_png_and_pdf_adds_missing_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            for extension, selected_filter in (("png", "PNG Files (*.png)"), ("pdf", "PDF Files (*.pdf)")):
                base = str(Path(temp) / f"pattern-{extension}")
                with patch("GUI.QFileDialog.getSaveFileName", return_value=(base, selected_filter)):
                    self.gui.on_save_figure()
                self.assertGreater(Path(base + "." + extension).stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
