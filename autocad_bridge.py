"""Standard-library-only Windows bridge; geometry arrives as JSON over stdin."""
import json
import sys
import threading
import time


class TransferCancelled(Exception):
    pass


def retry_com(operation, retries=3, delay=0.5):
    """Retry only explicit server-busy rejections, never arbitrary drawing errors."""
    for attempt in range(retries):
        try:
            return operation()
        except Exception as exc:
            code = getattr(exc, "hresult", None)
            busy = code in (-2147418111, -2147417846) or "Call was rejected by callee" in str(exc)
            if not busy or attempt == retries - 1:
                raise
            time.sleep(delay)


def write_geometry(geometry, pythoncom, connect, point, retry, progress=None, cancelled=None):
    """Write one undo group on the calling COM thread, including on cancellation."""
    pythoncom.CoInitialize()
    acad = model = doc = None
    undo_started = False
    try:
        acad = connect()
        model = retry(lambda: acad.model)
        doc = retry(lambda: acad.doc)
        retry(doc.StartUndoMark)
        undo_started = True
        shapes = geometry["shapes"]
        for index, shape in enumerate(shapes):
            if cancelled and cancelled():
                raise TransferCancelled("Transfer cancelled. Use Undo in AutoCAD to remove partial geometry.")
            if geometry["shape_type"] == "circle":
                retry(lambda: model.AddCircle(point(*shape), geometry["shape_radius"]))
            else:
                for i, start in enumerate(shape):
                    if cancelled and cancelled():
                        raise TransferCancelled("Transfer cancelled. Use Undo in AutoCAD to remove partial geometry.")
                    end = shape[(i + 1) % len(shape)]
                    retry(lambda: model.AddLine(point(*start), point(*end)))
            if progress and ((index + 1) % 25 == 0 or index + 1 == len(shapes)):
                progress(index + 1, len(shapes))
        for radius in geometry["center_circle_radii"]:
            if cancelled and cancelled():
                raise TransferCancelled("Transfer cancelled. Use Undo in AutoCAD to remove partial geometry.")
            retry(lambda: model.AddCircle(point(0, 0), radius))
        if cancelled and cancelled():
            raise TransferCancelled("Transfer cancelled. Use Undo in AutoCAD to remove partial geometry.")
    finally:
        active_error = sys.exc_info()[0] is not None
        try:
            if undo_started:
                retry(doc.EndUndoMark)
        except Exception:
            if not active_error:
                raise
        finally:
            model = doc = acad = None
            pythoncom.CoUninitialize()


def main():
    def emit(event, **values):
        print("AUTOCAD_BRIDGE " + json.dumps(dict(event=event, **values)), flush=True)

    try:
        if sys.platform != "win32":
            raise RuntimeError("The AutoCAD bridge must run with Windows Python.")
        try:
            import pythoncom
            from pyautocad import Autocad, APoint
        except (ImportError, OSError) as exc:
            raise RuntimeError("Install the Windows bridge dependencies with: python -m pip install pyautocad pywin32") from exc
        geometry = json.loads(sys.stdin.readline())
        stop = threading.Event()

        def listen():
            for line in sys.stdin:
                if line.strip() == "cancel":
                    stop.set()
                    return

        threading.Thread(target=listen, daemon=True).start()

        def connect():
            acad = Autocad(create_if_not_exists=True)
            _ = acad.model
            return acad

        write_geometry(geometry, pythoncom, lambda: retry_com(connect), APoint, retry_com,
                       lambda done, total: emit("progress", done=done, total=total), stop.is_set)
        emit("success")
        return 0
    except TransferCancelled as exc:
        emit("cancelled", message=str(exc))
        return 2
    except Exception as exc:
        emit("error", message=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
