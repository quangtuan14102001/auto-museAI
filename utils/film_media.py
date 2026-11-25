"""Frame extraction and deterministic film assembly with bundled FFmpeg."""
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from core.media_output import validate_output, validate_video_input, validate_stream
from core.models import JobMode
from utils.file_utils import find_ffmpeg_binary


def ffmpeg():
    binary = find_ffmpeg_binary()
    if not binary:
        raise ValueError("Không tìm thấy FFmpeg.")
    return binary


def run_ffmpeg(arguments, stop=None, timeout=900):
    if stop and stop():
        raise RuntimeError("Đã dừng xử lý video.")
    process = subprocess.Popen(
        [ffmpeg(), "-nostdin", "-hide_banner", "-v", "error", *map(str, arguments)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    started = time.monotonic()
    try:
        while True:
            try:
                output, error = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if (stop and stop()) or time.monotonic() - started > timeout:
                    raise RuntimeError("Đã dừng xử lý video." if stop and stop() else "FFmpeg không hoàn tất xử lý file.")
        if process.returncode:
            raise ValueError("FFmpeg: " + error.decode("utf-8", errors="replace")[-1000:])
        return output.decode("utf-8", errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def probe_video(path):
    validate_video_input(str(path))
    result = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, timeout=30,
                            creationflags=0x08000000 if os.name == "nt" else 0)
    text = result.stderr.decode("utf-8", errors="replace")
    duration = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", text)
    video_line = next((line for line in text.splitlines() if "Video:" in line), "")
    size = re.search(r"\b(\d{2,5})x(\d{2,5})\b", video_line)
    rate = re.search(r"([\d.]+) fps", video_line)
    if not duration or not size:
        raise ValueError("Không đọc được kích thước hoặc thời lượng video.")
    return {"duration": int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3]),
            "width": int(size[1]), "height": int(size[2]),
            "fps": float(rate[1]) if rate else 24.0, "audio": "Audio:" in text}


def validate_timeline(path, seconds, fps=24, stop=None):
    # Decode the entire video: a readable first frame does not prove that all
    # clips in a long movie are valid or that its video lasts as long as audio.
    text = run_ffmpeg(["-xerror", "-i", path, "-map", "0:v:0", "-an",
                       "-progress", "pipe:1", "-nostats", "-f", "null", "-"], stop)
    times = re.findall(r"^out_time_us=(\d+)$", text, re.MULTILINE)
    if not times or abs(int(times[-1]) / 1_000_000 - seconds) > max(0.08, 2 / fps):
        raise ValueError("Luồng hình không đủ hoặc không đúng thời lượng kế hoạch; không tự lặp/kéo chậm clip.")


def normalize_clip(source, destination, seconds, size=(1280, 720), fps=24, stop=None):
    info = probe_video(source)
    if seconds <= 0 or info["duration"] + 1 / fps < seconds:
        raise ValueError(f"Clip chỉ dài {info['duration']:.2f}s, cần {seconds:.2f}s. Nhập clip đủ dài hoặc tạo lại.")
    width, height = size
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("Kích thước xuất phải là số chẵn dương.")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".normalize-", dir=destination.parent) as temp:
        output = str(Path(temp) / "clip.mp4")
        args = ["-y", "-i", source]
        if not info["audio"]:
            args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        args += ["-map", "0:v:0", "-map", "0:a:0" if info["audio"] else "1:a:0",
                 "-vf", f"setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}",
                 "-af", "aresample=48000,asetpts=PTS-STARTPTS,apad", "-t", str(seconds),
                 "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", output]
        run_ffmpeg(args, stop)
        validate_timeline(output, seconds, fps, stop)
        os.replace(output, destination)
    return str(destination)


def extract_frame(source, destination, last=False, stop=None):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".frame-", dir=destination.parent) as temp:
        output = str(Path(temp) / "frame.png")
        args = ["-y"] + (["-sseof", "-1"] if last else []) + ["-i", source, "-map", "0:v:0", "-an"]
        if last:
            # Updating a single file leaves the last DECODED frame, not an
            # approximate seek frame or a memory-heavy reverse of the clip.
            args += ["-fps_mode", "passthrough", "-update", "1"]
        else:
            args += ["-frames:v", "1"]
        run_ffmpeg([*args, output], stop)
        validate_output(output, JobMode.TEXT_TO_IMAGE.value)
        os.replace(output, destination)
    return str(destination)


def extract_frame_at(source, destination, seconds, stop=None):
    """Decode one frame at a known timeline position, for sampled visual QA."""
    if seconds < 0:
        raise ValueError('Thời điểm khung hình phải không âm.')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.frame-', dir=destination.parent) as temp:
        output = str(Path(temp)/'frame.png')
        run_ffmpeg(['-y', '-ss', str(seconds), '-i', source, '-map', '0:v:0',
                    '-an', '-frames:v', '1', output], stop)
        validate_output(output, JobMode.TEXT_TO_IMAGE.value)
        os.replace(output, destination)
    return str(destination)


def assemble_film(store, destination, music="", narration="", keep_clip_audio=True, stop=None, progress=None):
    project = store.project
    if not project.ready_to_export:
        raise ValueError("Cần tạo và chấp nhận tất cả clip trước khi ghép phim.")
    clips = [store.asset(shot.clip) for shot in project.shots]
    destination = Path(destination).resolve()
    if str(destination).lower() in {str(Path(path).resolve()).lower() for path in clips}:
        raise ValueError("File phim không được trùng với clip đầu vào.")
    for index, (shot, path) in enumerate(zip(project.shots, clips)):
        store.check_integrity(shot)
        info = probe_video(path)
        if (info["width"], info["height"]) != (project.width, project.height) or abs(info["fps"] - project.fps) > 0.02 or not info["audio"]:
            raise ValueError(f"Clip #{index + 1} chưa đúng chuẩn hình/FPS/âm thanh của dự án. Nhập lại clip để chuẩn hóa.")
        validate_timeline(path, shot.timeline_seconds, project.fps, stop)
        if progress:
            progress(int((index + 1) / len(clips) * 35), f"Đã kiểm tra clip {index + 1}/{len(clips)}")
    for audio in [music, narration]:
        if audio:
            validate_stream(audio, "audio")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".film-export-", dir=destination.parent) as temp:
        listing = Path(temp) / "clips.txt"
        listing.write_text("ffconcat version 1.0\n" + "".join(
            "file '" + path.replace("\\", "/").replace("'", "'\\''") + "'\n" for path in clips
        ), encoding="utf-8")
        joined = str(Path(temp) / "joined.mp4")
        run_ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", "-movflags", "+faststart", joined], stop)
        if progress:
            progress(55, "Đã nối đúng thứ tự; đang hoàn thiện âm thanh")
        output = joined
        if music or narration or not keep_clip_audio:
            output = str(Path(temp) / "movie.mp4")
            args = ["-y", "-i", joined]
            filters = [f"[0:a]volume={1 if keep_clip_audio else 0}[base]"]
            labels = ["[base]"]
            number = 1
            for path, gain, loop in [(music, 0.15, True), (narration, 1.0, False)]:
                if not path:
                    continue
                if loop:
                    args += ["-stream_loop", "-1"]
                args += ["-i", path]
                filters.append(f"[{number}:a]aresample=48000,asetpts=PTS-STARTPTS,volume={gain}[audio{number}]")
                labels.append(f"[audio{number}]")
                number += 1
            filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95[aout]")
            args += ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[aout]",
                     "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2",
                     "-t", str(project.target_seconds), "-movflags", "+faststart", output]
            run_ffmpeg(args, stop)
        validate_output(output, JobMode.TEXT_TO_VIDEO.value)
        validate_timeline(output, project.target_seconds, project.fps, stop)
        os.replace(output, destination)
    if progress:
        progress(100, "Phim đã được kiểm tra toàn bộ luồng hình")
    return str(destination)
