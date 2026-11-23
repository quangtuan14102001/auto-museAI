import sys
import datetime
from PyQt6.QtCore import QObject, pyqtSignal


class LogEmitter(QObject):
    log_received = pyqtSignal(str, str, str) # timestamp, level, message


_emitter = LogEmitter()


def get_log_emitter() -> LogEmitter:
    return _emitter


def log_event(message: str, level: str = "INFO"):
    """
    Emits log event formatted for live console.
    level: INFO, SUCCESS, WARNING, ERROR, DEBUG
    """
    now = datetime.datetime.now().strftime("%H:%M:%S")
    # Clean prefix
    if not message.startswith("[Muse Chrome]") and not message.startswith("[System]"):
        full_msg = f"[Muse Chrome] {message}"
    else:
        full_msg = message

    _emitter.log_received.emit(now, level, full_msg)
    try:
        print(f"[{now}] [{level}] {full_msg}")
    except UnicodeEncodeError:
        try:
            safe_msg = full_msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
            print(f"[{now}] [{level}] {safe_msg}")
        except Exception:
            pass
