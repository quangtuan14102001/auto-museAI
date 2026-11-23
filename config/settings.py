import os
import sys
import shutil
import json
import logging
from typing import Dict, List, Optional
from core.models import ProfileItem, AliasItem, TaskItem
from core.selectors import MuseSelectors

logger = logging.getLogger("AutoMuse.Settings")


class SettingsManager:
    """
    Singleton-style configuration and data manager.
    Loads and saves project_config.json.
    """
    _instance: Optional["SettingsManager"] = None

    def __init__(self, config_path: str = "config/project_config.json"):
        self.config_path = os.path.abspath(config_path)
        config_dir = os.path.dirname(self.config_path)
        self.data_root = os.path.dirname(config_dir) if os.path.basename(config_dir).lower() == 'config' else config_dir
        self.app_config: dict = {
            "theme": "obsidian_dark",
            "font_size": 13,
            "output_dir": "output",
            "default_timeout": 210,
            "default_aspect_ratio": "16:9",
            "default_mode": "TEXT -> VIDEO",
            "default_video_duration": 5,
            "max_concurrent_tabs": 2,
            "auto_retry_count": 2,
            "proxy": "",
            "auto_new_chat": True,
            "update_manifest_url": ""
        }
        self.muse_selectors = MuseSelectors()
        self.llm_config: dict = {
            "provider": "gemini",
            "openai_api_key": "",
            "openai_model": "gpt-4o",
            "gemini_api_key": "",
            "gemini_model": "auto",
            "anthropic_api_key": "",
            "anthropic_model": "claude-3-5-sonnet-20241022"
        }
        self.tts_config: dict = {
            "provider": "edge-tts",
            "edge_voice": "vi-VN-HoaiMyNeural",
            "rate": "+0%",
            "pitch": "+0Hz",
            "elevenlabs_api_key": "",
            "elevenlabs_voice_id": "",
            "fpt_api_key": "",
            "fpt_voice": "banmai"
        }
        self.profiles: List[ProfileItem] = []
        self.aliases: List[AliasItem] = []
        self.tasks: List[TaskItem] = []

        self.load()

    @classmethod
    def get_instance(cls, config_path: str = "config/project_config.json") -> "SettingsManager":
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance

    def load(self):
        if not os.path.exists(self.config_path):
            candidates = []
            if hasattr(sys, "_MEIPASS"):
                candidates.append(os.path.join(sys._MEIPASS, "config", "project_config.json"))
            if getattr(sys, "frozen", False):
                candidates.append(os.path.join(os.path.dirname(sys.executable), "_internal", "config", "project_config.json"))
            for cand in candidates:
                if os.path.exists(cand):
                    try:
                        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                        shutil.copyfile(cand, self.config_path)
                        break
                    except Exception:
                        pass
            if not os.path.exists(self.config_path):
                self.save()
                return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "app" in data:
                self.app_config.update({key: value for key, value in data["app"].items()
                                        if key not in {"github_repo", "auto_check_update"}})

            if "muse_ai" in data:
                muse_data = data["muse_ai"]
                if "selectors" in muse_data:
                    self.muse_selectors = MuseSelectors.from_dict(muse_data["selectors"])
                if "base_url" in muse_data:
                    self.muse_selectors.base_url = muse_data["base_url"]
                if "studio_url" in muse_data:
                    self.muse_selectors.studio_url = muse_data["studio_url"]

            if "llm" in data:
                self.llm_config.update(data["llm"])
            if self.llm_config.get("gemini_model") == "gemini-1.5-flash":
                self.llm_config["gemini_model"] = "auto"

            if "tts" in data:
                self.tts_config.update(data["tts"])

            self.profiles = [ProfileItem.from_dict(p) for p in data.get("profiles", [])]
            for profile in self.profiles:
                profile.path = self.resolve_profile_path(profile.path)
            self.aliases = [AliasItem.from_dict(a) for a in data.get("aliases", [])]
            self.tasks = [TaskItem.from_dict(t) for t in data.get("tasks", [])]

            # Ensure default profiles exist if empty
            if not self.profiles:
                self.profiles = [
                    ProfileItem(id="so1", name="so1", path=self.profile_directory('so1'), enabled=True),
                    ProfileItem(id="so2", name="so2", path=self.profile_directory('so2'), enabled=True)
                ]

        except Exception as e:
            logger.error(f"Error loading config from {self.config_path}: {e}")

    def profile_directory(self, name):
        """New accounts belong beside this configuration, never a legacy copy."""
        return os.path.abspath(os.path.join(self.data_root, 'profiles', name))

    def resolve_profile_path(self, path):
        if os.path.isabs(path):
            return os.path.normpath(path)
        preferred = os.path.abspath(os.path.join(self.data_root, path))
        if os.path.isdir(preferred):
            return preferred
        # Preserve legacy development profiles only when no profile exists in
        # this app's data directory. Never override a newly connected account.
        project_dir = os.path.dirname(self.data_root)
        if (os.path.basename(self.data_root).lower() == 'dist'
                and os.path.isfile(os.path.join(project_dir, 'main.py'))
                and os.path.isfile(os.path.join(project_dir, 'AutoMuseAI.spec'))):
            legacy = os.path.abspath(os.path.join(project_dir, path))
            if os.path.isdir(legacy):
                return legacy
        return preferred

    def save(self):
        try:
            for retired_key in ("github_repo", "auto_check_update"):
                self.app_config.pop(retired_key, None)
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = {
                "app": self.app_config,
                "muse_ai": {
                    "base_url": self.muse_selectors.base_url,
                    "studio_url": self.muse_selectors.studio_url,
                    "selectors": {
                        "composer_textarea": self.muse_selectors.composer_textarea,
                        "file_input": self.muse_selectors.file_input,
                        "submit_button": self.muse_selectors.submit_button,
                        "aspect_ratio_button": self.muse_selectors.aspect_ratio_button,
                        "progress_indicators": self.muse_selectors.progress_indicators,
                        "completed_media": self.muse_selectors.completed_media,
                        "quota_warning": self.muse_selectors.quota_warning,
                    }
                },
                "llm": self.llm_config,
                "tts": self.tts_config,
                "profiles": [p.to_dict() for p in self.profiles],
                "aliases": [a.to_dict() for a in self.aliases],
                "tasks": [t.to_dict() for t in self.tasks]
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving config to {self.config_path}: {e}")

    def get_alias_dict(self) -> Dict[str, AliasItem]:
        return {a.tag: a for a in self.aliases}

    def get_enabled_profiles(self) -> List[ProfileItem]:
        return [p for p in self.profiles if p.enabled]
