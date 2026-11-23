import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.app_update import read_release, download_release, get_https, install_release


class AppUpdateTests(unittest.TestCase):
    def setUp(self):
        self.data = b"MZ" + b"installer fixture" * 30
        self.release = {"version": "9.0.0", "installer_url": "https://example.com/setup.exe",
                        "size": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest()}

    def response(self, body):
        result = MagicMock(status_code=200, url="https://example.com/file")
        result.__enter__.return_value = result
        result.iter_content.return_value = [body[:20], body[20:]]
        return result

    def test_newer_release_is_validated(self):
        with patch("core.app_update.requests.get", return_value=self.response(json.dumps(self.release).encode())):
            self.assertEqual(read_release("https://example.com/latest.json", "1.0.0"), self.release)

    def test_current_version_does_not_download(self):
        self.release["version"] = "1.0.0"
        with patch("core.app_update.requests.get", return_value=self.response(json.dumps(self.release).encode())):
            self.assertIsNone(read_release("https://example.com/latest.json", "1.0.0"))

    def test_insecure_redirect_is_blocked_before_request(self):
        response = MagicMock(status_code=302, headers={"Location": "http://example.com/bad"})
        with patch("core.app_update.requests.get", return_value=response) as get:
            with self.assertRaises(ValueError):
                get_https("https://example.com/latest.json")
            self.assertEqual(get.call_count, 1)

    def test_bad_metadata_never_reaches_installer(self):
        for key, value in [("sha256", "bad"), ("size", -1), ("version", "../../bad"),
                           ("installer_url", "http://example.com/setup.exe")]:
            with self.subTest(key=key):
                release = dict(self.release, **{key: value})
                with patch("core.app_update.requests.get", return_value=self.response(json.dumps(release).encode())):
                    with self.assertRaises(ValueError):
                        read_release("https://example.com/latest.json", "1.0.0")

    def test_verified_download_is_published_atomically(self):
        with tempfile.TemporaryDirectory() as root, patch("core.app_update.requests.get", return_value=self.response(self.data)):
            progress = []
            target = Path(download_release(self.release, progress.append, lambda: False, root))
            self.assertEqual(target.read_bytes(), self.data)
            self.assertEqual(progress[-1], 100)
            self.assertFalse(target.with_name("setup.part").exists())

    def test_corrupt_or_cancelled_download_leaves_no_executable(self):
        for cancelled in (True, False):
            with self.subTest(cancelled=cancelled), tempfile.TemporaryDirectory() as root:
                with patch("core.app_update.requests.get", return_value=self.response(b"MZcorrupt")):
                    with self.assertRaises((ValueError, InterruptedError)):
                        download_release(self.release, lambda _: None, lambda: cancelled, root)
                self.assertFalse(list(Path(root).rglob("*.exe")))
                self.assertFalse(list(Path(root).rglob("*.part")))

    def test_install_uses_existing_directory_without_shell(self):
        with tempfile.TemporaryDirectory() as root, patch("core.app_update.subprocess.Popen") as launch:
            installer = str(Path(root) / "setup.exe")
            app = str(Path(root) / "user app")
            install_release(installer, app)
            self.assertIn(f"/DIR={Path(app).resolve()}", launch.call_args.args[0])
            self.assertIn("/UPDATEAPP=1", launch.call_args.args[0])
            self.assertFalse(launch.call_args.kwargs["shell"])
