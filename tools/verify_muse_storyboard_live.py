"""Run one text-only Muse storyboard using the user's selected local profile."""
import json
import os
import sys
import threading
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from config.settings import SettingsManager
from workers.muse_storyboard_worker import MuseStoryboardWorker
from workers.film_storyboard_worker import apply_storyboard
from core.film_project import FilmStore
from ui.dialogs.film_dialog import FilmDialog

app = QApplication([])
settings = SettingsManager(str(ROOT/'dist/config/project_config.json'))
SettingsManager._instance = settings
profile = next(p for p in settings.profiles if p.enabled)
target = ROOT/'build/muse-storyboard-180s-live'
target.mkdir(parents=True, exist_ok=True)
worker = MuseStoryboardWorker('mèo và chuột', 180, 10, '', profile, settings.muse_selectors,
    settings.app_config.get('proxy', ''), checkpoint_path=target/'draft.json')
worker.response_timeout = 180
worker.progress.connect(print)
ready, errors = [], []
worker.storyboard_ready.connect(ready.append)
worker.error_signal.connect(errors.append)
timer = threading.Timer(210, worker.stop)
timer.start()
try:
    worker.run()
finally:
    timer.cancel()
if errors or not ready:
    print(errors[0] if errors else 'No storyboard returned')
    sys.exit(1)
project = apply_storyboard(ready[0], 'Mèo và chuột', 180, 10, '16:9', profile.id, '')
dialog = FilmDialog()
dialog.minutes.setValue(3)
dialog.seconds.setValue(0)
dialog._storyboard_received(ready[0])
assert dialog.storyboard_draft and dialog.script.toPlainText().strip()
dialog.close()
store = FilmStore(target/'project.film.json', project)
store.save()
report = {'shots': len(project.shots), 'seconds': project.target_seconds, 'source': 'muse',
          'ui_received_storyboard': True, 'media_requests': 0, 'project': str(store.manifest)}
(target/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
