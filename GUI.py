"""
GUI with 1-or-2 Defects Handling and AutoCAD Retry

Author: Ali Aslan Demir
GitHub: https://github.com/aliaslandemir/autocadmicropattern
"""

import sys
import math
import time
import numpy as np

import pythoncom  # For COM initialization
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog,
    QMessageBox, QRadioButton, QButtonGroup, QGroupBox
)
from PyQt5.QtCore import Qt

import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Attempt to import pyautocad
try:
    from pyautocad import Autocad, APoint
    PYAUTOCAD_AVAILABLE = True
except ImportError:
    PYAUTOCAD_AVAILABLE = False


# ----------------------------------------------------------------
# AutoCAD connection with a simple retry loop
# ----------------------------------------------------------------
def get_autocad_instance(retries=3, delay=0.5):
    """
    Attempt to create or connect to AutoCAD. Retry on COM errors
    like "Call was rejected by callee."
    """
    for attempt in range(retries):
        try:
            pythoncom.CoInitialize()
            acad = Autocad(create_if_not_exists=True)
            return acad
        except Exception as e:
            msg = str(e)
            if "Call was rejected by callee" in msg:
                time.sleep(delay)
            else:
                raise
    # If we get here, we failed all retries
    raise RuntimeError("Failed to connect to AutoCAD after multiple attempts.")


# ----------------------------------------------------------------
# Hex Grid + Orientation Functions
# ----------------------------------------------------------------
def generate_hex_grid(radius, side_length):
    """
    Return Nx2 array of (x,y) centers for a hexagonal grid.
    """
    q, r = np.meshgrid(range(-radius, radius + 1), range(-radius, radius + 1))
    mask = np.abs(q + r) <= radius
    x = 1.5 * side_length * q[mask]
    y = np.sqrt(3) * side_length * (r[mask] + 0.5 * q[mask])
    return np.vstack((x, y)).T

def hexagon_xy(center, size):
    """
    Return arrays x[], y[] describing the perimeter of a single hexagon.
    """
    angles = np.linspace(0, 2 * np.pi, 7)
    x = center[0] + size * np.cos(angles)
    y = center[1] + size * np.sin(angles)
    return x, y

def orientation_angle_1_defect(center, defect, theta0, m):
    """
    For ONE defect, use a vortex-like formula from 'Role of tissue...' references:
       theta(r) = theta0 + m * arctan2( (y - y_def), (x - x_def) )
    """
    dx = center[0] - defect[0]
    dy = center[1] - defect[1]
    return theta0 + m * math.atan2(dy, dx)

def orientation_angle_2_defects(center, defects, theta0):
    """
    For TWO defects, sum up the angles to each defect, then offset by theta0.
    This was used in earlier scripts/figures (sum-of-angles approach).
       theta(r) = theta0 + sum( atan2(y - y_def, x - x_def) )
    """
    angle_sum = 0.0
    for d in defects:
        dx = center[0] - d[0]
        dy = center[1] - d[1]
        angle_sum += math.atan2(dy, dx)
    return angle_sum + theta0

# ----------------------------------------------------------------
# AutoCAD geometry
# ----------------------------------------------------------------
def rotate_point(x, y, angle_radians):
    c = math.cos(angle_radians)
    s = math.sin(angle_radians)
    return (x*c - y*s, x*s + y*c)

def add_rectangle(acad, center, width, height, angle_degrees):
    angle_rad = math.radians(angle_degrees)
    corners = [
        (-width/2, -height/2),
        ( width/2, -height/2),
        ( width/2,  height/2),
        (-width/2,  height/2)
    ]
    rotated = [rotate_point(x, y, angle_rad) for (x, y) in corners]
    translated = [APoint(center[0] + p[0], center[1] + p[1]) for p in rotated]
    for i in range(len(translated)):
        start_pt = translated[i]
        end_pt   = translated[(i + 1) % len(translated)]
        acad.model.AddLine(start_pt, end_pt)

def add_circle(acad, center, radius):
    acad.model.AddCircle(APoint(center[0], center[1]), radius)

def transfer_to_autocad(radius, side_length, one_or_two,
                        defect1, defect2,
                        theta0, m, rect_w, rect_h,
                        circle_r, circle_r2):
    """
    Main function for transferring geometry to AutoCAD. 
    We connect to AutoCAD with a small retry loop.
    """
    acad = get_autocad_instance()

    # Generate the grid
    hex_centers = generate_hex_grid(radius, side_length)

    for c in hex_centers:
        # Decide orientation angle depending on 1 or 2 defects
        if one_or_two == 1:
            angle_radians = orientation_angle_1_defect(c, defect1, math.radians(theta0), m)
        else:
            # 2-defect approach
            angle_radians = orientation_angle_2_defects(c, [defect1, defect2], math.radians(theta0))
        angle_degrees = math.degrees(angle_radians) % 360

        # Place a rectangle
        add_rectangle(acad, c, rect_w, rect_h, angle_degrees)

    # Add two circles in the center
    add_circle(acad, (0,0), circle_r)
    add_circle(acad, (0,0), circle_r2)


# ----------------------------------------------------------------
# Embedded Matplotlib Canvas
# ----------------------------------------------------------------
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=6, height=6, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.ax = self.fig.add_subplot(111)
        super(MplCanvas, self).__init__(self.fig)

    def draw_hex_grid(self, radius, side_length, one_or_two,
                      defect1, defect2,
                      theta0, m, rect_w, rect_h):
        """
        Plot the hex grid + orientation rectangles in this canvas.
        """
        from matplotlib.patches import Rectangle
        from matplotlib.transforms import Affine2D
        from matplotlib.cm import hsv

        self.ax.clear()
        centers = generate_hex_grid(radius, side_length)

        # For color mapping, we might map angles to [0..1] in hue
        # We'll store angles in radians, then shift them to [0..1].
        angles_radians = []

        # Compute orientation angle for each center
        for c in centers:
            if one_or_two == 1:
                ang_rad = orientation_angle_1_defect(
                    center=c, 
                    defect=defect1,
                    theta0=math.radians(theta0),
                    m=m
                )
            else:
                ang_rad = orientation_angle_2_defects(
                    center=c,
                    defects=[defect1, defect2],
                    theta0=math.radians(theta0)
                )
            angles_radians.append(ang_rad)

        # Plot hexagons
        for c in centers:
            hx, hy = hexagon_xy(c, side_length)
            self.ax.fill(hx, hy, facecolor='lightgray', edgecolor='gray', linewidth=1)

        # Now draw rectangles at each center
        for (c, ang_rad) in zip(centers, angles_radians):
            # Map angle to [0..1] for an HSV colormap
            # We do angle in [ -pi..pi ], shift up so 0..2pi => [0..1].
            # Or just mod it: hue = (ang_rad % (2*pi)) / (2*pi).
            hue = (ang_rad % (2*math.pi)) / (2*math.pi)
            color = hsv(hue)

            rect = Rectangle(
                xy=(-rect_w/2, -rect_h/2),
                width=rect_w,
                height=rect_h,
                color=color,
                alpha=0.5
            )
            t = (Affine2D()
                 .rotate_around(0, 0, ang_rad)
                 .translate(c[0], c[1])
                 + self.ax.transData)
            rect.set_transform(t)
            self.ax.add_patch(rect)

            # Show numeric angle in degrees
            deg_val = math.degrees(ang_rad)
            self.ax.text(c[0], c[1], f"{deg_val:.0f}°",
                         ha='center', va='center', fontsize=8)

        # Draw defect(s) and center
        self.ax.scatter([0], [0], color='red', label='Center', zorder=5)
        if one_or_two == 1:
            self.ax.scatter([defect1[0]], [defect1[1]], color='blue', label='Defect')
        else:
            self.ax.scatter([defect1[0], defect2[0]],
                            [defect1[1], defect2[1]],
                            color='blue', label='Defects')

        self.ax.set_aspect('equal', 'box')
        self.ax.grid(True, linestyle='--')
        self.ax.axhline(y=0, color='k', linewidth=1)
        self.ax.axvline(x=0, color='k', linewidth=1)
        if len(centers) > 0:
            margin = side_length * 2
            xvals, yvals = centers[:,0], centers[:,1]
            self.ax.set_xlim(xvals.min() - margin, xvals.max() + margin)
            self.ax.set_ylim(yvals.min() - margin, yvals.max() + margin)
        self.ax.legend()
        self.ax.set_title("Nematic Defects in Hexagonal Grid")
        self.draw()


# ----------------------------------------------------------------
# The Main PyQt5 GUI
# ----------------------------------------------------------------
class AdvancedHexGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hex Grid & AutoCAD Transfer")
        self.setMinimumSize(1200, 700)

        # Main Layout: Horizontal
        main_layout = QHBoxLayout(self)
        self.setLayout(main_layout)

        # Left: Matplotlib Canvas
        self.canvas = MplCanvas(self, width=6, height=6, dpi=100)
        main_layout.addWidget(self.canvas, stretch=2)

        # Right: Parameter panel + logging
        right_panel = QVBoxLayout()
        main_layout.addLayout(right_panel, stretch=1)

        form_layout = QGridLayout()
        right_panel.addLayout(form_layout)

        row = 0

        # 1) Hex Grid Radius
        form_layout.addWidget(QLabel("Hex Grid Radius:"), row, 0)
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
        form_layout.addWidget(QLabel("Circle Radius:"), row, 0)
        self.circle_r_input = QLineEdit("45")
        form_layout.addWidget(self.circle_r_input, row, 1)
        row += 1

        # 11) Circle Radius 2
        form_layout.addWidget(QLabel("Circle Radius 2:"), row, 0)
        self.circle_r2_input = QLineEdit("45")
        form_layout.addWidget(self.circle_r2_input, row, 1)
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

        # Log / Status
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("Log messages / status here...")
        right_panel.addWidget(self.log_area)

        # Make sure the second defect line is set according to default radio:
        self.on_defect_radio_changed(self.radio_group.checkedId())

    def on_defect_radio_changed(self, id_):
        """
        Enable/disable second defect input based on the chosen radio.
        """
        if id_ == 1:
            # 1 Defect
            self.def2_input.setEnabled(False)
        else:
            # 2 Defects
            self.def2_input.setEnabled(True)

    def parse_defect(self, text):
        """
        Parse "x,y" from a string.
        Returns (x,y) as floats or None if invalid.
        """
        try:
            x_str, y_str = text.split(",")
            return (float(x_str.strip()), float(y_str.strip()))
        except:
            return None

    def get_parameters(self):
        """
        Read parameters from the GUI, return a dict or None on error.
        """
        try:
            radius = int(self.radius_input.text())
            side_len = float(self.side_len_input.text())
            rect_w = float(self.rect_w_input.text())
            rect_h = float(self.rect_h_input.text())
            one_or_two = self.radio_group.checkedId()  # 1 or 2
            def1 = self.parse_defect(self.def1_input.text())
            def2 = self.parse_defect(self.def2_input.text())
            theta0_deg = float(self.theta0_input.text())
            m_val = float(self.m_input.text())
            circle_r = float(self.circle_r_input.text())
            circle_r2 = float(self.circle_r2_input.text())

            if one_or_two == 1:
                # Must have a valid defect1
                if def1 is None:
                    raise ValueError("Defect #1 is invalid.")
            else:
                # Must have valid defect1 + defect2
                if def1 is None or def2 is None:
                    raise ValueError("One or both defects invalid for 2 defects.")
            
            return {
                'radius': radius,
                'side_length': side_len,
                'rect_w': rect_w,
                'rect_h': rect_h,
                'one_or_two': one_or_two,
                'def1': def1,
                'def2': def2,
                'theta0_deg': theta0_deg,
                'm_val': m_val,
                'circle_r': circle_r,
                'circle_r2': circle_r2
            }

        except ValueError as ve:
            self.log_area.append(f"Parameter error: {ve}")
            return None

    def on_generate(self):
        """
        Generate the hex‐grid model in the embedded Matplotlib canvas.
        """
        params = self.get_parameters()
        if not params:
            return
        self.log_area.append("Generating model...")

        try:
            # Draw on canvas
            self.canvas.draw_hex_grid(
                radius=params['radius'],
                side_length=params['side_length'],
                one_or_two=params['one_or_two'],
                defect1=params['def1'],
                defect2=params['def2'] if params['def2'] else (0,0),
                theta0=params['theta0_deg'],
                m=params['m_val'],
                rect_w=params['rect_w'],
                rect_h=params['rect_h']
            )
            self.log_area.append("Model displayed on the left.")
        except Exception as e:
            self.log_area.append(f"Error generating model: {e}")

    def on_save_figure(self):
        """
        Save the current figure to disk.
        """
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Figure", "",
                "PNG Files (*.png);;PDF Files (*.pdf);;All Files (*)"
            )
            if filename:
                self.canvas.fig.savefig(filename)
                self.log_area.append(f"Figure saved to: {filename}")
        except Exception as e:
            self.log_area.append(f"Error saving figure: {e}")

    def on_transfer(self):
        """
        Transfer geometry to AutoCAD, with retry logic to avoid COM errors.
        """
        if not PYAUTOCAD_AVAILABLE:
            QMessageBox.warning(self, "Error", 
                                "pyautocad not installed or not found.")
            return

        params = self.get_parameters()
        if not params:
            return
        self.log_area.append("Transferring to AutoCAD...")

        try:
            transfer_to_autocad(
                radius=params['radius'],
                side_length=params['side_length'],
                one_or_two=params['one_or_two'],
                defect1=params['def1'] if params['def1'] else (0,0),
                defect2=params['def2'] if params['def2'] else (0,0),
                theta0=params['theta0_deg'],
                m=params['m_val'],
                rect_w=params['rect_w'],
                rect_h=params['rect_h'],
                circle_r=params['circle_r'],
                circle_r2=params['circle_r2']
            )
            self.log_area.append("Transfer to AutoCAD complete.")
        except Exception as e:
            self.log_area.append(f"Error transferring to AutoCAD: {e}")


def main():
    app = QApplication(sys.argv)
    gui = AdvancedHexGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
