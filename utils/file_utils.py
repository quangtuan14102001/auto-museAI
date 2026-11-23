import os
import re
import sys
import uuid
import shutil
import subprocess
from typing import Optional


def ensure_dir(path: str) -> str:
    """Ensures directory exists and returns absolute path."""
    abs_path = os.path.abspath(path)
    os.makedirs(abs_path, exist_ok=True)
    return abs_path


def open_in_explorer(target_path: str):
    """Opens directory or selects file in Windows Explorer."""
    abs_path = os.path.abspath(target_path)
    if not os.path.exists(abs_path):
        os.makedirs(abs_path, exist_ok=True)

    if sys.platform == "win32":
        if os.path.isfile(abs_path):
            subprocess.Popen(["explorer", "/select,", abs_path])
        else:
            os.startfile(abs_path)
    else:
        # Fallback for cross-platform
        subprocess.Popen(["xdg-open", abs_path])


def sanitize_filename(name: str, max_len: int = 50) -> str:
    """Sanitizes string for safe filename."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned[:max_len]


def generate_output_filename(
    output_dir: str,
    profile_name: str,
    task_index: int,
    ext: str = "mp4"
) -> str:
    """
    Constructs path matching requirement:
    [OutputDir]/[Profile]/Prompt_[Index]_[JobID].[ext]
    """
    clean_profile = sanitize_filename(profile_name) or "default"
    dir_path = os.path.join(output_dir, clean_profile)
    ensure_dir(dir_path)

    short_id = uuid.uuid4().hex[:6]
    clean_ext = ext.lstrip(".")
    filename = f"Prompt_{task_index:03d}_{short_id}.{clean_ext}"
    return os.path.join(dir_path, filename)


def find_ffmpeg_binary() -> Optional[str]:
    """Finds ffmpeg executable on local dir, bundled dir, or system PATH."""
    base_dirs = [
        os.getcwd(),
        os.path.join(os.getcwd(), "bin"),
    ]
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        base_dirs.extend([
            exe_dir,
            os.path.join(exe_dir, "bin"),
            os.path.join(exe_dir, "_internal"),
            os.path.join(exe_dir, "_internal", "bin"),
        ])
        if hasattr(sys, "_MEIPASS"):
            base_dirs.extend([
                sys._MEIPASS,
                os.path.join(sys._MEIPASS, "bin"),
            ])

    for d in base_dirs:
        cand = os.path.join(d, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        if os.path.exists(cand) and os.path.isfile(cand):
            return cand

    return shutil.which("ffmpeg")


def find_chromium_executable(headless: bool = False) -> Optional[str]:
    """
    Finds the best available Chromium executable:
    Prefer the same full Chrome executable for login and automation, including
    headless automation. A headless shell is only a fallback when Chrome is absent.
    """
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    base_dirs = []

    # 1. Packaged PyInstaller paths
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        base_dirs.append(os.path.join(exe_dir, "_internal", "playwright", "driver", "package", ".local-browsers"))
        base_dirs.append(os.path.join(exe_dir, "browsers"))
        if hasattr(sys, "_MEIPASS"):
            base_dirs.append(os.path.join(sys._MEIPASS, "playwright", "driver", "package", ".local-browsers"))
            base_dirs.append(os.path.join(sys._MEIPASS, "browsers"))

    # 2. Python site-packages playwright driver path
    try:
        import playwright
        p_dir = os.path.dirname(playwright.__file__)
        base_dirs.append(os.path.join(p_dir, "driver", "package", ".local-browsers"))
    except Exception:
        pass

    # 3. System ms-playwright
    if local_app_data:
        base_dirs.append(os.path.join(local_app_data, "ms-playwright"))

    headless_candidates = []
    chrome_candidates = []

    for b_dir in base_dirs:
        if not os.path.exists(b_dir):
            continue
        for root, dirs, files in os.walk(b_dir):
            for f in files:
                f_lower = f.lower()
                if f_lower == "chrome-headless-shell.exe":
                    headless_candidates.append(os.path.join(root, f))
                elif f_lower == "chrome.exe":
                    chrome_candidates.append(os.path.join(root, f))

    if chrome_candidates:
        return chrome_candidates[0]

    if headless and headless_candidates:
        return headless_candidates[0]

    return None

