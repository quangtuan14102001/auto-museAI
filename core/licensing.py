"""Online license checks. No issuer secret or offline unlock flag in the client."""
import hashlib
import os
from pathlib import Path
import sys
import time
import uuid
import winreg

import requests

from core.license_source import LICENSE_SERVER_URL


def device_id():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            identity = winreg.QueryValueEx(key, "MachineGuid")[0]
    except OSError:
        raise ValueError("Chưa đọc được mã máy Windows. Vui lòng kiểm tra quyền hệ thống.")
    return hashlib.sha256(("AutoMuseAI/v1/" + str(identity)).encode()).hexdigest()


def _credential_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AutoMuseAI' / 'license.dat'


def _protect(data, decrypt=False):
    # Windows DPAPI ties the saved key to the current Windows user.
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('Không đọc/lưu được key bản quyền cho tài khoản Windows này.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel = ctypes.WinDLL('kernel32')
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def saved_key():
    try:
        return _protect(_credential_path().read_bytes(), decrypt=True).decode()
    except (OSError, ValueError, UnicodeError):
        return ''


def save_key(key):
    path = _credential_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(_protect(key.encode()))
    os.replace(temporary, path)


class LicenseSession:
    def __init__(self, url=LICENSE_SERVER_URL):
        self.url = url.rstrip('/')
        self.key = saved_key()
        self.deadline = 0
        self.description = ''

    @property
    def valid(self):
        return bool(self.key and time.monotonic() < self.deadline)

    def check(self, key=None):
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            self.deadline = 0
            raise ValueError('Nhà phát hành chưa cấu hình máy chủ bản quyền HTTPS. Liên hệ người bán.')
        candidate = (key if key is not None else self.key).strip()
        if not candidate:
            self.deadline = 0
            raise ValueError('Vui lòng nhập key bản quyền.')
        try:
            response = requests.post(self.url + '/v1/check', json={'key': candidate, 'device': device_id()},
                                     timeout=(10, 20), allow_redirects=False)
            if response.status_code != 200:
                messages = {401: 'Key không hợp lệ.', 403: 'Key đã bị khóa.',
                            410: 'Key đã hết hạn. Liên hệ người bán để gia hạn.',
                            409: 'Key đã đủ số máy. Liên hệ người bán để chuyển máy.',
                            429: 'Đã thử quá nhiều lần. Vui lòng đợi một phút.'}
                raise ValueError(messages.get(response.status_code, 'Máy chủ bản quyền chưa sẵn sàng. Thử lại sau.'))
            result = response.json()
            ttl = result['ttl']
            if result.get('active') is not True or type(ttl) is not int or not 0 < ttl <= 300:
                raise ValueError('Thông tin bản quyền từ máy chủ không hợp lệ.')
            save_key(candidate)
            self.key = candidate
            self.deadline = time.monotonic() + ttl
            self.description = f"Key {result['license_id'][:8]} · Hạn: {result.get('expires_at') or 'Vĩnh viễn'}"
        except (requests.RequestException, KeyError, TypeError) as exc:
            self.deadline = 0
            raise ValueError('Chưa kết nối được máy chủ bản quyền. Kiểm tra mạng và thử lại.') from None
        except ValueError:
            self.deadline = 0
            raise
