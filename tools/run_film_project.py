"""Open the app and run an explicitly selected film project to export.

Uses the same public project/worker flow as the GUI. It never approves a dialog,
logs in, or resubmits an interrupted scene automatically. stop.request pauses it.
"""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--working-directory", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    project = Path(args.project).resolve()
    sys.path.insert(0, str(root))
    os.chdir(args.working_directory)
    os.environ["PATH"] = str(root / "bin") + os.pathsep + os.environ.get("PATH", "")
    stream = (project.parent / "run.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = stream

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from workers.film_worker import FilmWorker, FilmExportWorker

    app = QApplication([])
    window = MainWindow()
    window.show()
    window._open_film_dialog(str(project))
    dialog = window.film_dialog
    paused = False
    finished = False

    def pause_on_error(_):
        nonlocal paused
        paused = True

    original_launch = dialog._launch
    def launch(worker):
        worker.failed.connect(pause_on_error)
        original_launch(worker)
    dialog._launch = launch

    def tick():
        nonlocal paused, finished
        film = dialog.store.project
        request = project.parent / "stop.request"
        if request.exists():
            paused = True
            dialog._stop()
            request.unlink()
        if dialog.worker and (getattr(dialog.worker, "stopped", False) or getattr(dialog.worker, "_stop_requested", False)):
            paused = True
        if not dialog.working and not paused and not finished:
            if film.state == "EXPORTED" and film.export_file:
                finished = True
                dialog.tabs.setCurrentIndex(3)
            elif film.ready_to_export:
                dialog._export()
        status = {
            "state": film.state, "paused": paused, "working": dialog.working,
            "approved": sum(shot.status == "APPROVED" for shot in film.shots),
            "total": len(film.shots), "target_seconds": film.target_seconds,
            "current_message": dialog.status.text(),
            "export_file": dialog.store.asset(film.export_file) if film.export_file else "",
        }
        temporary = project.parent / "run-status.tmp"
        temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, project.parent / "run-status.json")

    timer = QTimer(window)
    timer.setInterval(2000)
    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(500, dialog._start)
    app.exec()


if __name__ == "__main__":
    main()
