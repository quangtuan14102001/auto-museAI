"""Explicit live Gemini + offscreen UI verification; no Muse media requests.

Reads local credentials without printing or copying them into the report.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from config.settings import SettingsManager
from workers.film_storyboard_worker import FilmStoryboardWorker, apply_storyboard
from core.film_project import FilmStore
from ui.dialogs.film_dialog import FilmDialog


def main():
    config = ROOT / "dist/config/project_config.json"
    if not config.exists():
        config = ROOT / "config/project_config.json"
    settings = SettingsManager(str(config))
    llm = settings.llm_config
    if not llm.get("gemini_api_key"):
        raise SystemExit("No local Gemini API key configured.")
    target = ROOT / "build/storyboard-180s-live-v1.2.8"
    target.mkdir(parents=True, exist_ok=True)
    worker = FilmStoryboardWorker("mèo và chuột", 180, 10, "", "gemini", llm["gemini_api_key"],
                                  sys.argv[1] if len(sys.argv) > 1 else llm.get("gemini_model", "auto"),
                                  checkpoint_path=target / "draft.json")
    ready, errors = [], []
    worker.storyboard_ready.connect(ready.append)
    worker.error_signal.connect(errors.append)
    worker.progress.connect(print)
    worker.run()
    if errors or not ready:
        print(errors[0] if errors else "No completed storyboard returned.")
        return 1
    payload = ready[0]
    profile_id = next((p.id for p in settings.profiles if p.name == "so1"), "")
    project = apply_storyboard(payload, "Mèo và chuột", 180, 10, "16:9", profile_id, "")
    app = QApplication.instance() or QApplication([])
    SettingsManager._instance = settings
    dialog = FilmDialog()
    dialog.minutes.setValue(3)
    dialog.seconds.setValue(0)
    dialog.idea.setPlainText("mèo và chuột")
    dialog._storyboard_received(payload)
    report = {"shots": len(project.shots), "seconds": project.target_seconds,
              "continuations": sum(s.continuation for s in project.shots),
              "boundaries_match": all(not b.continuation or b.start_state == a.end_state
                                      for a, b in zip(project.shots, project.shots[1:])),
              "ui_received_storyboard": dialog.storyboard_draft == payload,
              "ui_script_populated": bool(dialog.script.toPlainText().strip()),
              "model": worker.model_name, "muse_requests": 0}
    if report["ui_received_storyboard"] and report["boundaries_match"]:
        store = FilmStore(target / "project.film.json", project)
        store.save()
        report["project"] = str(store.manifest)
    dialog.close()
    (target / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["ui_received_storyboard"] and report["boundaries_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
