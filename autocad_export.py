"""Native Windows COM export and WSL-to-Windows Python integration."""
import sys
import os
import json
import shutil
import subprocess
import threading
import queue
from pathlib import Path

from autocad_bridge import TransferCancelled, write_geometry, retry_com

from geometry import generate_hex_grid, orientation_angles, shape_vertices

pythoncom = Autocad = APoint = None
AUTOCAD_IMPORT_ERROR = "AutoCAD transfer requires Windows Python, pyautocad, and pywin32."
if sys.platform == "win32":
    try:
        import pythoncom
        from pyautocad import Autocad, APoint
    except (ImportError, OSError) as exc:
        AUTOCAD_IMPORT_ERROR += f" ({exc})"
PYAUTOCAD_AVAILABLE = all(item is not None for item in (pythoncom, Autocad, APoint))


def is_wsl():
    if sys.platform != "linux":
        return False
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
    except OSError:
        return False


WSL_AVAILABLE = is_wsl()
AUTOCAD_AVAILABLE = PYAUTOCAD_AVAILABLE or WSL_AVAILABLE


def get_autocad_instance(retries=3, delay=0.5):
    if not PYAUTOCAD_AVAILABLE:
        raise RuntimeError(AUTOCAD_IMPORT_ERROR)

    def connect():
        acad = Autocad(create_if_not_exists=True)
        # pyautocad connects lazily; force a COM call while retry is active.
        _ = acad.model
        return acad

    return retry_com(connect, retries, delay)


def geometry_payload(params):
    params.validate()
    centers = generate_hex_grid(params.radius, params.side_length)
    if params.shape_type == "circle":
        shapes = centers.tolist()
    else:
        shapes = shape_vertices(centers, orientation_angles(centers, params), params).tolist()
    return {"shape_type": params.shape_type, "shapes": shapes,
            "shape_radius": params.shape_circle_r if params.shape_type == "circle" else None,
            "center_circle_radii": params.center_circle_radii}


def windows_python_command():
    """Resolve an explicit interpreter or a Windows launcher without a shell."""
    configured = os.environ.get("AUTOCAD_WINDOWS_PYTHON")
    if configured:
        if "\\" in configured or (len(configured) > 1 and configured[1] == ":"):
            try:
                configured = subprocess.run(["wslpath", "-u", configured], check=True,
                                            capture_output=True, text=True, timeout=10).stdout.strip()
            except (OSError, subprocess.SubprocessError) as exc:
                raise RuntimeError("Cannot convert AUTOCAD_WINDOWS_PYTHON to a WSL path.") from exc
        return [configured]
    launcher = shutil.which("py.exe")
    if launcher:
        return [launcher, "-3"]
    # Conda is often absent from the Windows PATH; find standard per-user installs.
    root = Path("/mnt/c/Users")
    if root.is_dir():
        for name in ("miniforge3", "miniconda3", "anaconda3"):
            for candidate in sorted(root.glob(f"*/{name}/python.exe")):
                return [str(candidate)]
    python = shutil.which("python.exe")
    if python:
        return [python]
    raise RuntimeError("Windows Python was not found. Set AUTOCAD_WINDOWS_PYTHON to its python.exe path.")


def transfer_via_windows(geometry, progress=None, cancelled=None):
    if cancelled and cancelled():
        raise TransferCancelled("Transfer cancelled before connecting to AutoCAD.")
    # Code and JSON on pipes avoid shared files and Windows checkout paths.
    source = Path(__file__).with_name("autocad_bridge.py").read_text(encoding="utf-8")
    command = windows_python_command() + ["-u", "-c", source]
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                   errors="replace", bufsize=1,
                                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except OSError as exc:
        raise RuntimeError("Cannot launch Windows Python. Set AUTOCAD_WINDOWS_PYTHON to a working Windows python.exe; check WSL interop is enabled.") from exc
    messages = queue.Queue()

    def read_output():
        try:
            for line in process.stdout:
                messages.put(line)
        finally:
            messages.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    terminal = None
    diagnostics = []
    cancel_sent = False
    try:
        try:
            process.stdin.write(json.dumps(geometry, allow_nan=False) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            # Read the child's setup error even if it exited before accepting JSON.
            pass
        while True:
            if cancelled and cancelled() and not cancel_sent:
                try:
                    process.stdin.write("cancel\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                cancel_sent = True
            try:
                line = messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                break
            if line.startswith("AUTOCAD_BRIDGE "):
                event = json.loads(line[len("AUTOCAD_BRIDGE "):])
                if event["event"] == "progress":
                    if progress:
                        progress(event["done"], event["total"])
                else:
                    terminal = event
            else:
                diagnostics.append(line.strip())
                diagnostics = diagnostics[-10:]
        code = process.wait()
        if terminal and terminal["event"] == "cancelled":
            raise TransferCancelled(terminal["message"])
        if terminal and terminal["event"] == "error":
            raise RuntimeError(terminal["message"])
        if code != 0 or not terminal or terminal["event"] != "success":
            detail = " ".join(diagnostics)
            raise RuntimeError(f"Windows Python bridge exited without completing (exit {code}). {detail} "
                               "Check AUTOCAD_WINDOWS_PYTHON and install pyautocad and pywin32 in that Windows environment.")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
        reader.join(timeout=2)
        try:
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        process.stdout.close()


def transfer_to_autocad(params, progress=None, cancelled=None):
    """Use native COM or a Windows process from WSL, with one undo group."""
    params.validate()
    if not PYAUTOCAD_AVAILABLE:
        if WSL_AVAILABLE:
            return transfer_via_windows(geometry_payload(params), progress, cancelled)
        raise RuntimeError(AUTOCAD_IMPORT_ERROR)
    write_geometry(geometry_payload(params), pythoncom, get_autocad_instance, APoint,
                   retry_com, progress, cancelled)
