"""Live acceptance: real providers + real dialog callbacks/save/reopen.

Only the local folder picker is supplied by the harness; provider calls and
storyboard validation are not mocked. No image/video worker is started.
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication
import requests
from config.settings import SettingsManager
from core.film_content import inspect_project
from core.film_project import validate_continuity
from core.version import APP_VERSION
from ui.dialogs.film_dialog import FilmDialog


def run_source(app, source, directory, idea, seconds, model, notes='', min_continuations=0):
    config = ROOT / 'dist/config/project_config.json'
    settings = SettingsManager(str(config))
    SettingsManager._instance = settings
    settings.app_config['output_dir'] = str(directory / 'drafts')
    settings.llm_config['provider'] = 'gemini'
    if model:
        settings.llm_config['gemini_model'] = model
    dialog = FilmDialog()
    dialog.minutes.setValue(seconds // 60)
    dialog.seconds.setValue(seconds % 60)
    dialog.idea.setPlainText(idea)
    dialog.notes.setPlainText(notes)
    dialog.script_source.setCurrentIndex(0 if source == 'muse' else 1)
    errors, warnings, http_errors = [], [], []
    original_post = requests.post
    secret = settings.llm_config.get('gemini_api_key', '')

    def observed_post(*args, **kwargs):
        response = original_post(*args, **kwargs)
        if response.status_code >= 400:
            try:
                error = response.json().get('error', {})
                message = str(error.get('message', ''))
                if secret:
                    message = message.replace(secret, '[redacted]')
                http_errors.append({'http': response.status_code, 'status': error.get('status'), 'message': message[:700]})
            except ValueError:
                http_errors.append({'http': response.status_code, 'status': 'non-JSON response'})
        return response

    directory.mkdir(parents=True, exist_ok=True)
    result = {'source': source, 'app_version': APP_VERSION, 'idea': idea, 'requested_seconds': seconds,
              'expected_clips': math.ceil(seconds / 10), 'media_requests': 0, 'result': 'FAIL'}
    with patch('requests.post', side_effect=observed_post):
        dialog._generate_script()
        worker = dialog.script_worker
        if worker:
            if source == 'muse':
                close = worker._close
                async def close_with_evidence():
                    try:
                        if worker.page and not worker.page.is_closed():
                            await worker.page.screenshot(path=str(directory/'muse-session.png'))
                    finally:
                        await close()
                worker._close = close_with_evidence
            loop = QEventLoop()
            worker.progress.connect(lambda text: print(f'[{source}] {text}', flush=True))
            worker.error_signal.connect(errors.append)
            worker.finished.connect(loop.quit)
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: getattr(worker, 'stop', lambda: None)())
            timer.start(240_000)
            if worker.isRunning():
                loop.exec()
            app.processEvents()
            timer.stop()
        if dialog.storyboard_draft:
            # Use the app's actual Create plan handler and persistence path.
            with patch('ui.dialogs.film_dialog.QFileDialog.getExistingDirectory', return_value=str(directory)), \
                 patch('ui.dialogs.film_dialog.QMessageBox.warning', side_effect=lambda *a: warnings.append(a[-1])):
                dialog._create()
            if dialog.store:
                manifest = dialog.store.manifest
                expected = [s.prompt for s in dialog.store.project.shots]
                reopened = FilmDialog()
                reopened.load_project(str(manifest))
                project = reopened.store.project
                validate_continuity(project)
                content = inspect_project(project)
                ok = (len(project.shots) == result['expected_clips']
                      and sum(s.timeline_seconds for s in project.shots) == seconds
                      and [s.prompt for s in project.shots] == expected
                      and reopened.table.rowCount() == len(project.shots)
                      and sum(s.continuation for s in project.shots) >= min_continuations
                      and not content)
                result.update(result='PASS' if ok else 'FAIL', clips=len(project.shots),
                    timeline_seconds=sum(s.timeline_seconds for s in project.shots), saved_and_reopened=True,
                    ui_table_rows=reopened.table.rowCount(), content_issues=len(content), project=str(manifest),
                    continuations=sum(s.continuation for s in project.shots), references=len(project.references))
                reopened.resize(1200, 900)
                reopened.show()
                app.processEvents()
                reopened.grab().save(str(directory / 'reopened-project.png'))
                reopened.close()
        result.update(errors=errors, warnings=warnings, http_errors=http_errors, final_status=dialog.status.text())
    dialog.close()
    (directory/'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', choices=['both', 'gemini', 'muse'], default='both')
    parser.add_argument('--model', default='')
    parser.add_argument('--idea', default='mèo và chuột')
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--notes', default='')
    parser.add_argument('--min-continuations', type=int, default=0)
    parser.add_argument('--run-dir', default='')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    root = Path(args.run_dir) if args.run_dir else ROOT / 'build' / ('live-film-idea-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    results = [run_source(app, source, root/source, args.idea, args.seconds, args.model, args.notes, args.min_continuations)
               for source in (['gemini', 'muse'] if args.source == 'both' else [args.source])]
    print('Report directory:', root, flush=True)
    return 0 if all(r['result'] == 'PASS' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
