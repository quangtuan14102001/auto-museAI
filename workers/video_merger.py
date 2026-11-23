import os
import subprocess
import tempfile
from typing import List
from PyQt6.QtCore import QThread, pyqtSignal
from utils.file_utils import find_ffmpeg_binary, ensure_dir
from utils.logger import log_event
from core.media_output import validate_output, validate_video_input
from core.models import JobMode


class VideoMergerWorker(QThread):
    progress_signal = pyqtSignal(int, str) # percent, status
    finished_signal = pyqtSignal(str) # output_filepath
    error_signal = pyqtSignal(str)

    def __init__(self, video_files: List[str], output_path: str):
        super().__init__()
        self.video_files = video_files
        self.output_path = output_path

    def run(self):
        if not self.video_files:
            self.error_signal.emit("Danh sách video để ghép rỗng!")
            return

        ffmpeg_bin = find_ffmpeg_binary()
        if not ffmpeg_bin:
            self.error_signal.emit("Không tìm thấy ffmpeg trên hệ thống. Vui lòng cài đặt FFmpeg.")
            return

        ensure_dir(os.path.dirname(os.path.abspath(self.output_path)))

        self.progress_signal.emit(10, f"Đang chuẩn bị ghép {len(self.video_files)} video...")
        log_event(f"Bắt đầu ghép {len(self.video_files)} video bằng FFmpeg...")

        list_file = None
        try:
            for video in self.video_files:
                validate_video_input(video)
                if os.path.normcase(os.path.abspath(video)) == os.path.normcase(os.path.abspath(self.output_path)):
                    raise ValueError("File xuất không được trùng với video đầu vào.")
            # Create a temporary concat list file
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
                list_file = f.name
                for v in self.video_files:
                    # FFmpeg concat requires escaped single quotes
                    safe_path = os.path.abspath(v).replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")

            self.progress_signal.emit(30, "Đang xử lý luồng FFmpeg Concat...")

            # Attempt stream copy first (ultra fast)
            cmd = [
                ffmpeg_bin,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c", "copy",
                self.output_path
            ]

            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  encoding="utf-8", errors="replace",
                                  creationflags=0x08000000 if os.name == "nt" else 0)

            if proc.returncode != 0:
                # If stream copy failed (e.g. codecs/resolutions differ), re-encode with h264
                self.progress_signal.emit(50, "Đang re-encode chuẩn hóa khung hình...")
                cmd_reencode = [
                    ffmpeg_bin,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", list_file,
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "22",
                    "-c:a", "aac",
                    self.output_path
                ]
                proc_re = subprocess.run(cmd_reencode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                         encoding="utf-8", errors="replace",
                                         creationflags=0x08000000 if os.name == "nt" else 0)
                if proc_re.returncode != 0:
                    raise Exception(f"FFmpeg error: {proc_re.stderr}")

            # Clean up temp file
            try:
                os.remove(list_file)
            except Exception:
                pass

            validate_output(self.output_path, JobMode.TEXT_TO_VIDEO.value)
            self.progress_signal.emit(100, "Hoàn tất ghép video!")
            log_event(f"Ghép video thành công: {self.output_path}", "SUCCESS")
            self.finished_signal.emit(self.output_path)

        except Exception as e:
            log_event(f"Lỗi khi ghép video: {e}", "ERROR")
            self.error_signal.emit(str(e))
        finally:
            if list_file and os.path.exists(list_file):
                os.remove(list_file)
