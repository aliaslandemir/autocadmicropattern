"""
Hexagonal micropattern preview and optional AutoCAD export

Author: Ali Aslan Demir
GitHub: https://github.com/aliaslandemir/autocadmicropattern
"""

import sys
import math
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog,
    QRadioButton, QButtonGroup, QGroupBox, QComboBox, QCheckBox,
    QScrollArea, QProgressBar
)
from PyQt5.QtCore import QThread, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.collections import PolyCollection, PatchCollection
from matplotlib.patches import Circle
from matplotlib import colormaps

from geometry import (
    PatternParameters, generate_hex_grid, orientation_angles, shape_vertices,
)
from autocad_export import (
    AUTOCAD_AVAILABLE, AUTOCAD_IMPORT_ERROR, transfer_to_autocad, TransferCancelled,
)


class TransferWorker(QThread):
    progress = pyqtSignal(int, int)
    succeeded = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, params, parent=None):
        super().__init__(parent)
        self.params = params

    def run(self):
        try:
            transfer_to_autocad(self.params, self.progress.emit, self.isInterruptionRequested)
        except TransferCancelled as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Transfer failed: {exc}. Partial geometry may remain; use Undo in AutoCAD.")
        else:
            self.succeeded.emit()


class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=6, height=6, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, layout="constrained")
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)

    def draw_hex_grid(self, params, show_grid=True, show_angles=True):
        params.validate()
        centers = generate_hex_grid(params.radius, params.side_length)
        angles = orientation_angles(centers, params)
        self.ax.clear()
        if show_grid:
            hex_angles = np.arange(6) * math.pi / 3
            offsets = params.side_length * np.column_stack((np.cos(hex_angles), np.sin(hex_angles)))
            self.ax.add_collection(PolyCollection(
                centers[:, None, :] + offsets, facecolors="#eeeeee",
                edgecolors="#aaaaaa", linewidths=0.5, zorder=1))

        colors = colormaps["hsv"]((angles % (2 * math.pi)) / (2 * math.pi))
        if params.shape_type == "circle":
            shapes = PatchCollection(
                [Circle(center, params.shape_circle_r) for center in centers],
                facecolors=colors, edgecolors="black", linewidths=0.5, alpha=0.5, zorder=2)
            shape_min = centers.min(axis=0) - params.shape_circle_r
            shape_max = centers.max(axis=0) + params.shape_circle_r
        else:
            vertices = shape_vertices(centers, angles, params)
            shapes = PolyCollection(vertices, facecolors=colors, edgecolors="black",
                                    linewidths=0.5, alpha=0.5, zorder=2)
            shape_min = vertices.min(axis=(0, 1))
            shape_max = vertices.max(axis=(0, 1))
        self.ax.add_collection(shapes)
        # Thousands of text artists overwhelm both rendering and readability.
        if show_angles and len(centers) <= 500:
            for center, angle in zip(centers, angles):
                self.ax.text(*center, f"{math.degrees(angle) % 360:.0f}°",
                             ha="center", va="center", fontsize=7, zorder=3)

        for radius in params.center_circle_radii:
            self.ax.add_patch(Circle((0, 0), radius, fill=False, edgecolor="#333333",
                                     linewidth=1.2, zorder=4))
        self.ax.scatter([0], [0], color="red", label="Center", zorder=5)
        defects = np.asarray((params.defect1, params.defect2)[:params.one_or_two])
        self.ax.scatter(defects[:, 0], defects[:, 1], color="blue", marker="x",
                        label="Defect" if params.one_or_two == 1 else "Defects", zorder=5)
        ring_extent = max(params.center_circle_radii, default=0)
        lower = np.minimum.reduce([centers.min(axis=0) - params.side_length,
                                   shape_min, defects.min(axis=0), np.full(2, -ring_extent)])
        upper = np.maximum.reduce([centers.max(axis=0) + params.side_length,
                                   shape_max, defects.max(axis=0), np.full(2, ring_extent)])
        margin = max(params.side_length * 0.2, float(np.max(upper-lower)) * 0.04)
        self.ax.set_xlim(lower[0]-margin, upper[0]+margin)
        self.ax.set_ylim(lower[1]-margin, upper[1]+margin)
        self.ax.set_aspect("equal", "box")
        self.ax.set_xlabel("x (drawing units)")
        self.ax.set_ylabel("y (drawing units)")
        self.ax.grid(True, linestyle="--", alpha=0.25)
        self.ax.axhline(0, color="black", linewidth=0.5)
        self.ax.axvline(0, color="black", linewidth=0.5)
        self.ax.legend(loc="upper right")
        self.ax.set_title(f"{params.shape_type.title()} pattern · {len(centers):,} cells")
        self.draw()


# ----------------------------------------------------------------
# The Main PyQt5 GUI
# ----------------------------------------------------------------
class AdvancedHexGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hex Grid & AutoCAD Transfer")
        self.resize(1200, 800)
        self.setMinimumSize(850, 600)
        self.transfer_worker = None
        self.preview_parameters = None

        # Main Layout: Horizontal
        main_layout = QHBoxLayout(self)

        # Left: Matplotlib Canvas
        self.canvas = MplCanvas(self, width=6, height=6, dpi=100)
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        preview_layout.addWidget(self.canvas)
        main_layout.addLayout(preview_layout, stretch=2)

        # Right: Parameter panel + logging
        right_widget = QWidget()
        right_panel = QVBoxLayout(right_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right_widget)
        scroll.setMinimumWidth(350)
        main_layout.addWidget(scroll, stretch=1)

        form_layout = QGridLayout()
        right_panel.addLayout(form_layout)

        row = 0

        # 1) Hex Grid Radius
        form_layout.addWidget(QLabel("Hex Grid Radius (0–100):"), row, 0)
        self.radius_input = QLineEdit("9")
        form_layout.addWidget(self.radius_input, row, 1)
        row += 1

        # 2) Hex Side Length
        form_layout.addWidget(QLabel("Hex Side Length:"), row, 0)
        self.side_len_input = QLineEdit("16")
        form_layout.addWidget(self.side_len_input, row, 1)
        row += 1

        # 3) Rectangle Width
        form_layout.addWidget(QLabel("Rectangle Width:"), row, 0)
        self.rect_w_input = QLineEdit("22.4")
        form_layout.addWidget(self.rect_w_input, row, 1)
        row += 1

        # 4) Rectangle Height
        form_layout.addWidget(QLabel("Rectangle Height:"), row, 0)
        self.rect_h_input = QLineEdit("11.2")
        form_layout.addWidget(self.rect_h_input, row, 1)
        row += 1

        # 4b) Shape Selection
        form_layout.addWidget(QLabel("Shape Type:"), row, 0)
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["Rectangle", "Triangle", "Circle"])
        form_layout.addWidget(self.shape_combo, row, 1)
        row += 1

        # 4c) Triangle Edge Length (equilateral)
        form_layout.addWidget(QLabel("Triangle Edge Length:"), row, 0)
        self.triangle_edge_input = QLineEdit("12")
        form_layout.addWidget(self.triangle_edge_input, row, 1)
        row += 1

        # 4d) Circle Radius (per hex)
        form_layout.addWidget(QLabel("Shape Circle Radius:"), row, 0)
        self.shape_circle_r_input = QLineEdit("10")
        form_layout.addWidget(self.shape_circle_r_input, row, 1)
        row += 1

        # 5) Defect selection
        defect_group = QGroupBox("Number of Defects")
        defect_layout = QHBoxLayout(defect_group)
        self.radio_group = QButtonGroup(self)
        self.one_defect_radio = QRadioButton("1 Defect")
        self.two_defects_radio = QRadioButton("2 Defects")
        self.one_defect_radio.setChecked(True)
        self.radio_group.addButton(self.one_defect_radio, 1)
        self.radio_group.addButton(self.two_defects_radio, 2)
        defect_layout.addWidget(self.one_defect_radio)
        defect_layout.addWidget(self.two_defects_radio)
        form_layout.addWidget(defect_group, row, 0, 1, 2)
        row += 1

        # Connect a slot so we can enable/disable the second defect line
        self.radio_group.buttonClicked[int].connect(self.on_defect_radio_changed)
        self.shape_combo.currentTextChanged.connect(self.on_shape_changed)

        # 6) Defect #1
        form_layout.addWidget(QLabel("Defect #1 (x,y):"), row, 0)
        self.def1_input = QLineEdit("50,50")
        form_layout.addWidget(self.def1_input, row, 1)
        row += 1

        # 7) Defect #2
        form_layout.addWidget(QLabel("Defect #2 (x,y):"), row, 0)
        self.def2_input = QLineEdit("-50,-50")
        form_layout.addWidget(self.def2_input, row, 1)
        row += 1

        # 8) Angle Offset (theta0)
        form_layout.addWidget(QLabel("Angle Offset (θ₀, deg):"), row, 0)
        self.theta0_input = QLineEdit("0")
        form_layout.addWidget(self.theta0_input, row, 1)
        row += 1

        # 9) Angle Multiplier (m) for the 1-defect formula
        form_layout.addWidget(QLabel("Angle Multiplier (m):"), row, 0)
        self.m_input = QLineEdit("1")
        form_layout.addWidget(self.m_input, row, 1)
        row += 1

        # 10) Circle Radius
        form_layout.addWidget(QLabel("Center Ring 1 Radius:"), row, 0)
        self.circle_r_input = QLineEdit("45")
        self.circle_r_input.setToolTip("Use 0 to disable this center circle.")
        form_layout.addWidget(self.circle_r_input, row, 1)
        row += 1

        # 11) Circle Radius 2
        form_layout.addWidget(QLabel("Center Ring 2 Radius:"), row, 0)
        self.circle_r2_input = QLineEdit("45")
        self.circle_r2_input.setToolTip("Use 0 to disable this center circle. Equal radii create one circle.")
        form_layout.addWidget(self.circle_r2_input, row, 1)
        row += 1

        self.show_grid = QCheckBox("Show hexagonal grid")
        self.show_grid.setChecked(True)
        form_layout.addWidget(self.show_grid, row, 0, 1, 2)
        row += 1
        self.show_angles = QCheckBox("Show angles (up to 500 cells)")
        self.show_angles.setChecked(True)
        form_layout.addWidget(self.show_angles, row, 0, 1, 2)
        row += 1

        # Action Buttons
        self.gen_button = QPushButton("Generate Model")
        self.gen_button.clicked.connect(self.on_generate)
        form_layout.addWidget(self.gen_button, row, 0, 1, 2)
        row += 1

        self.save_button = QPushButton("Save Figure")
        self.save_button.clicked.connect(self.on_save_figure)
        form_layout.addWidget(self.save_button, row, 0, 1, 2)
        row += 1

        self.transfer_button = QPushButton("Transfer to AutoCAD")
        self.transfer_button.clicked.connect(self.on_transfer)
        form_layout.addWidget(self.transfer_button, row, 0, 1, 2)
        row += 1

        self.cancel_button = QPushButton("Cancel Transfer")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.on_cancel_transfer)
        form_layout.addWidget(self.cancel_button, row, 0, 1, 2)
        row += 1
        self.transfer_progress = QProgressBar()
        self.transfer_progress.setRange(0, 100)
        form_layout.addWidget(self.transfer_progress, row, 0, 1, 2)

        # Log / Status
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.document().setMaximumBlockCount(500)
        self.log_area.setMinimumHeight(100)
        self.log_area.setPlaceholderText("Log messages / status here...")
        right_panel.addWidget(self.log_area)

        # Make sure the second defect line is set according to default radio:
        self.on_defect_radio_changed(self.radio_group.checkedId())
        self.on_shape_changed(self.shape_combo.currentText())
        self.show_grid.toggled.connect(self.on_generate)
        self.show_angles.toggled.connect(self.on_generate)
        if not AUTOCAD_AVAILABLE:
            self.transfer_button.setEnabled(False)
            self.transfer_button.setToolTip(AUTOCAD_IMPORT_ERROR)
            self.log_area.append(AUTOCAD_IMPORT_ERROR + " Preview and image export are available.")
        self.on_generate()

    def on_defect_radio_changed(self, id_):
        """
        Enable/disable second defect input based on the chosen radio.
        """
        self.m_input.setEnabled(id_ == 1)
        if id_ == 1:
            # 1 Defect
            self.def2_input.setEnabled(False)
        else:
            # 2 Defects
            self.def2_input.setEnabled(True)

    def on_shape_changed(self, shape_text):
        """
        Enable dimension inputs based on selected primitive.
        """
        shape = (shape_text or "").lower()
        enable_rect = (shape == "rectangle")
        enable_tri = (shape == "triangle")
        enable_circle = (shape == "circle")

        self.rect_w_input.setEnabled(enable_rect)
        self.rect_h_input.setEnabled(enable_rect)
        self.triangle_edge_input.setEnabled(enable_tri)
        self.shape_circle_r_input.setEnabled(enable_circle)

    @staticmethod
    def parse_defect(text):
        try:
            x_str, y_str = text.split(",")
            result = (float(x_str.strip()), float(y_str.strip()))
            return result if all(math.isfinite(v) for v in result) else None
        except (ValueError, TypeError):
            return None

    def get_parameters(self):
        """Only parse fields used by the selected shape and defect mode."""
        try:
            def number(field, label):
                try:
                    return float(field.text())
                except ValueError:
                    raise ValueError(f"{label} must be a number.") from None

            shape = self.shape_combo.currentText().lower()
            count = self.radio_group.checkedId()
            try:
                radius = int(self.radius_input.text())
            except ValueError:
                raise ValueError("Hex grid radius must be a whole number.") from None
            params = PatternParameters(
                radius=radius,
                side_length=number(self.side_len_input, "Hex side length"),
                one_or_two=count,
                shape_type=shape,
                defect1=self.parse_defect(self.def1_input.text()),
                defect2=self.parse_defect(self.def2_input.text()) if count == 2 else (0, 0),
                theta0=number(self.theta0_input, "Angle offset"),
                m=number(self.m_input, "Angle multiplier") if count == 1 else 1.0,
                rect_w=number(self.rect_w_input, "Rectangle width") if shape == "rectangle" else 1.0,
                rect_h=number(self.rect_h_input, "Rectangle height") if shape == "rectangle" else 1.0,
                triangle_edge=number(self.triangle_edge_input, "Triangle edge length") if shape == "triangle" else 1.0,
                shape_circle_r=number(self.shape_circle_r_input, "Shape circle radius") if shape == "circle" else 1.0,
                circle_r=number(self.circle_r_input, "Center circle radius"),
                circle_r2=number(self.circle_r2_input, "Center circle radius 2"),
            )
            return params.validate()
        except ValueError as exc:
            self.log_area.append(f"Parameter error: {exc}")
            return None

    def on_generate(self):
        params = self.get_parameters()
        if params is None:
            return
        try:
            self.canvas.draw_hex_grid(params, self.show_grid.isChecked(), self.show_angles.isChecked())
            self.preview_parameters = params
            self.save_button.setEnabled(True)
            count = 1 + 3 * params.radius * (params.radius + 1)
            self.log_area.append(f"Displayed {count:,} {params.shape_type} cells.")
            if self.show_angles.isChecked() and count > 500:
                self.log_area.append("Angle labels hidden above 500 cells to keep the preview responsive.")
        except Exception as exc:
            self.preview_parameters = None
            self.save_button.setEnabled(False)
            self.log_area.append(f"Error generating model: {exc}")

    def on_save_figure(self):
        if self.preview_parameters is None:
            self.log_area.append("Generate a model before saving.")
            return
        try:
            filename, selected_filter = QFileDialog.getSaveFileName(
                self, "Save Figure", "pattern.png", "PNG Files (*.png);;PDF Files (*.pdf)")
            if filename:
                from pathlib import Path
                if not Path(filename).suffix:
                    filename += ".pdf" if selected_filter.startswith("PDF") else ".png"
                self.canvas.fig.savefig(filename, dpi=200)
                self.log_area.append(f"Figure saved to: {filename}")
        except Exception as exc:
            self.log_area.append(f"Error saving figure: {exc}")

    def on_transfer(self):
        if not AUTOCAD_AVAILABLE or self.transfer_worker is not None:
            return
        params = self.get_parameters()
        if params is None:
            return
        # Refresh the preview from the exact parameter snapshot being exported.
        try:
            self.canvas.draw_hex_grid(params, self.show_grid.isChecked(), self.show_angles.isChecked())
            self.preview_parameters = params
            self.save_button.setEnabled(True)
        except Exception as exc:
            self.log_area.append(f"Error generating model: {exc}")
            return
        self.transfer_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.transfer_progress.setRange(0, 0)
        self.log_area.append("Connecting and transferring to AutoCAD...")
        worker = TransferWorker(params, self)
        self.transfer_worker = worker
        worker.progress.connect(self.on_transfer_progress)
        worker.failed.connect(self.log_area.append)
        worker.succeeded.connect(self.on_transfer_succeeded)
        worker.finished.connect(self.on_transfer_finished)
        worker.start()

    def on_transfer_progress(self, done, total):
        self.transfer_progress.setRange(0, total)
        self.transfer_progress.setValue(done)

    def on_transfer_succeeded(self):
        self.transfer_progress.setRange(0, 100)
        self.transfer_progress.setValue(100)
        self.log_area.append("Transfer to AutoCAD complete.")

    def on_transfer_finished(self):
        self.transfer_worker.deleteLater()
        self.transfer_worker = None
        self.transfer_button.setEnabled(AUTOCAD_AVAILABLE)
        self.cancel_button.setEnabled(False)
        if self.transfer_progress.maximum() == 0:
            self.transfer_progress.setRange(0, 100)
            self.transfer_progress.setValue(0)

    def on_cancel_transfer(self):
        if self.transfer_worker is not None:
            self.transfer_worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.log_area.append("Cancellation requested; waiting for the current AutoCAD call.")

    def closeEvent(self, event):
        if self.transfer_worker is not None:
            self.on_cancel_transfer()
            self.log_area.append("Wait for the transfer to stop, then close the window.")
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    gui = AdvancedHexGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
