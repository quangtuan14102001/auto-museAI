"""Regression checks for browser profile selection in packaged builds."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import SettingsManager


class BuildProfilePathTests(unittest.TestCase):
    def test_profile_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").touch()
            (root / "AutoMuseAI.spec").touch()
            (root / "profiles/so1").mkdir(parents=True)
            config = root / "settings.json"
            config.write_text(json.dumps({"profiles": [
                {"id": "so1", "name": "so1", "path": "profiles/so1"},
                {"id": "so2", "name": "so2", "path": "profiles/so2"},
                {"id": "custom", "name": "custom", "path": str(root / "custom")},
            ]}), encoding="utf-8")
            for folder, development in [("dist", True), ("installed", False)]:
                with self.subTest(folder=folder), patch.object(sys, "frozen", True, create=True), patch.object(
                    sys, "executable", str(root / folder / "AutoMuseAI.exe")
                ):
                    settings = SettingsManager(str(config))
                    self.assertEqual(settings.profiles[0].path, str(root / "profiles/so1"))
                    self.assertEqual(settings.profiles[1].path, str(root / "profiles/so2"))
                    self.assertEqual(settings.profiles[2].path, str(root / "custom"))

    def test_new_dist_account_wins_over_old_root_profile_and_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'main.py').touch()
            (root/'AutoMuseAI.spec').touch()
            (root/'profiles/so1').mkdir(parents=True)
            preferred = root/'dist/profiles/so1'
            preferred.mkdir(parents=True)
            config = root/'dist/config/project_config.json'
            config.parent.mkdir()
            config.write_text(json.dumps({'profiles':[{'id':'so1','name':'so1','path':'profiles/so1'}]}))
            for frozen in (False, True):
                with patch.object(sys, 'frozen', frozen, create=True), patch.object(sys, 'executable', str(root/'dist/AutoMuseAI.exe')):
                    settings = SettingsManager(str(config))
                    self.assertEqual(settings.profiles[0].path, str(preferred))
                    settings.save()
                    reloaded = SettingsManager(str(config))
                    self.assertEqual(reloaded.profiles[0].path, str(preferred))

    def test_legacy_profile_reused_only_when_app_has_no_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'main.py').touch()
            (root/'AutoMuseAI.spec').touch()
            legacy = root/'profiles/so1'
            legacy.mkdir(parents=True)
            config = root/'dist/config/project_config.json'
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({'profiles':[{'id':'so1','name':'so1','path':'profiles/so1'}]}))
            settings = SettingsManager(str(config))
            self.assertEqual(settings.profiles[0].path, str(legacy))
            self.assertEqual(settings.profile_directory('so1'), str(root/'dist/profiles/so1'))

    def test_explicit_profile_is_never_switched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root/'config/project_config.json'
            config.parent.mkdir()
            explicit = root/'my-account'
            config.write_text(json.dumps({'profiles':[{'id':'so1','name':'so1','path':str(explicit)}]}))
            self.assertEqual(SettingsManager(str(config)).profiles[0].path, str(explicit))


if __name__ == "__main__":
    unittest.main()
