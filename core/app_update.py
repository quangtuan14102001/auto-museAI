"""Explicit, HTTPS-only installer updates. No startup network requests."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests

from core.version import APP_VERSION, is_newer_version

MAX_INSTALLER_BYTES = 1024 * 1024 * 1024


def https_url(value):
    if not isinstance(value, str):
        raise ValueError("Nguồn cập nhật phải là đường dẫn HTTPS hợp lệ.")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Nguồn cập nhật phải là đường dẫn HTTPS hợp lệ.")
    return value


def get_https(url, **kwargs):
    for _ in range(10):
        response = requests.get(https_url(url), allow_redirects=False, **kwargs)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        destination = urljoin(url, response.headers.get("Location", ""))
        response.close()
        url = https_url(destination)
    raise ValueError("Nguồn cập nhật chuyển hướng quá nhiều lần.")


def read_release(url, current=APP_VERSION):
    with get_https(url, timeout=(15, 45), stream=True) as response:
        response.raise_for_status()
        https_url(response.url)
        content = bytearray()
        for chunk in response.iter_content(8192):
            content.extend(chunk)
            if len(content) > 65536:
                raise ValueError("Thông tin cập nhật vượt kích thước cho phép.")
    release = json.loads(content)
    version = release.get("version", "")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Thông tin phiên bản cập nhật không hợp lệ.")
    if not is_newer_version(version, current):
        return None
    https_url(release.get("installer_url", ""))
    if not re.fullmatch(r"[a-fA-F0-9]{64}", release.get("sha256", "")):
        raise ValueError("Bản cập nhật thiếu mã kiểm tra SHA-256.")
    size = release.get("size")
    if type(size) is not int or not 0 < size <= MAX_INSTALLER_BYTES:
        raise ValueError("Kích thước bộ cài cập nhật không hợp lệ.")
    return release


def download_release(release, progress, cancelled, directory=None):
    root = Path(tempfile.mkdtemp(prefix="automuse-update-", dir=directory))
    partial, target = root / "setup.part", root / "setup.exe"
    received, digest = 0, hashlib.sha256()
    try:
        with get_https(release["installer_url"], stream=True, timeout=(15, 45)) as response:
            response.raise_for_status()
            https_url(response.url)
            with partial.open("wb") as stream:
                for chunk in response.iter_content(256 * 1024):
                    if cancelled():
                        raise InterruptedError("Đã hủy tải bản cập nhật.")
                    received += len(chunk)
                    if received > release["size"]:
                        raise ValueError("Bộ cài tải về vượt kích thước đã công bố.")
                    digest.update(chunk)
                    stream.write(chunk)
                    progress(int(received * 100 / release["size"]))
        if received != release["size"] or digest.hexdigest().lower() != release["sha256"].lower():
            raise ValueError("Bộ cài tải về chưa đầy đủ hoặc sai mã kiểm tra. Hãy thử cập nhật lại.")
        with partial.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("File tải về không phải bộ cài Windows.")
        os.replace(partial, target)
        return str(target)
    except Exception:
        partial.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise


def install_release(installer, app_directory):
    # Arguments remain separate; no shell interpolation or elevation is needed.
    return subprocess.Popen([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                             "/CLOSEAPPLICATIONS", "/UPDATEAPP=1", f"/DIR={Path(app_directory).resolve()}"],
                            cwd=str(Path(installer).parent), shell=False)
