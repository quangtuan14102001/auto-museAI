"""Validate generated media from its contents, never from a URL or MIME label."""
import os
import subprocess
from dataclasses import dataclass

from PyQt6.QtGui import QImage

from core.models import JobMode
from utils.file_utils import find_ffmpeg_binary


@dataclass(frozen=True)
class MediaFormat:
    kind: str
    extension: str


def expected_media_kind(mode: str) -> str:
    mode = JobMode(mode)  # Reject unknown modes instead of silently treating them as video.
    return "image" if mode == JobMode.TEXT_TO_IMAGE else "video"


def detect_media_format(data: bytes) -> MediaFormat | None:
    image_ext = None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        image_ext = "png"
    elif data.startswith(b"\xff\xd8\xff"):
        image_ext = "jpg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        image_ext = "webp"
    if image_ext:
        if not QImage.fromData(data).isNull():
            return MediaFormat("image", image_ext)
        return None
    if len(data) >= 16 and data[4:8] == b"ftyp":
        brands = data[8:12] + data[16:min(len(data), int.from_bytes(data[:4], "big"))]
        if any(brand in brands for brand in (b"isom", b"iso2", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"dash", b"qt  ")):
            return MediaFormat("video", "mp4")
    if data.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in data[:256]:
        return MediaFormat("video", "webm")
    return None


def validate_output(path: str, mode: str, *, probe_video: bool = True) -> MediaFormat:
    expected = expected_media_kind(mode)
    if not path or not os.path.isfile(path):
        raise ValueError("Chưa có file kết quả hợp lệ.")
    with open(path, "rb") as stream:
        media = detect_media_format(stream.read())
    if media is None:
        raise ValueError("File kết quả hỏng hoặc không phải ảnh/video được hỗ trợ.")
    if media.kind != expected:
        raise ValueError(f"Sai loại kết quả: chế độ {mode} cần {expected}, nhận được {media.kind}.")
    extension = os.path.splitext(path)[1].lower().lstrip(".")
    if extension not in ({"jpg", "jpeg"} if media.extension == "jpg" else {media.extension}):
        raise ValueError("Đuôi file kết quả không khớp định dạng thực tế.")
    if media.kind == "video" and probe_video:
        validate_stream(path, "video")
    return media


def validate_stream(path: str, kind: str) -> None:
    ffmpeg = find_ffmpeg_binary()
    if not ffmpeg:
        raise ValueError("Thiếu FFmpeg để kiểm tra file kết quả.")
    stream = "v" if kind == "video" else "a"
    result = subprocess.run(
        [ffmpeg, "-v", "error", "-nostdin", "-i", os.path.abspath(path),
         "-map", f"0:{stream}:0", f"-frames:{stream}", "1", "-f", "null", "-"],
        capture_output=True, timeout=30,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    if result.returncode:
        raise ValueError(f"File kết quả không có luồng {kind} giải mã được.")


def validate_audio_output(path: str) -> None:
    with open(path, "rb") as stream:
        header = stream.read(3)
    is_mp3 = header.startswith(b"ID3") or (
        len(header) == 3 and header[0] == 255 and header[1] & 224 == 224 and header[1] & 6 != 0
    )
    if not is_mp3:
        raise ValueError("Kết quả TTS không phải file MP3 hợp lệ.")
    validate_stream(path, "audio")


def validate_video_input(path: str) -> None:
    if not os.path.isfile(path):
        raise ValueError("Không tìm thấy video đầu vào.")
    with open(path, "rb") as stream:
        media = detect_media_format(stream.read())
    if media is not None and media.kind == "image":
        raise ValueError("Đầu vào ghép video là ảnh tĩnh.")
    validate_stream(path, "video")


def build_generation_prompt(task) -> str:
    kind = expected_media_kind(task.mode)
    aspect = f" Tỷ lệ khung hình {task.aspect_ratio}." if task.aspect_ratio and task.aspect_ratio != "AUTO" else ""
    if kind == "image":
        instruction = "Tạo một ảnh tĩnh duy nhất theo mô tả dưới đây. Chỉ xuất ảnh, không tạo video hoặc ảnh động."
    elif task.mode == JobMode.REFERENCE_IMAGE_TO_VIDEO.value:
        instruction = f"Tạo một video {task.video_duration} giây từ ảnh tham chiếu đã tải lên theo mô tả dưới đây. Chỉ xuất video."
    elif task.mode == JobMode.TEXT_TO_VIDEO.value:
        instruction = f"Tạo một video {task.video_duration} giây theo mô tả dưới đây. Chỉ xuất video."
    else:
        raise ValueError("Chế độ hai bước phải được tách thành bước tạo ảnh và bước tạo video.")
    provider = ""
    if kind == "video":
        provider = (
            "\nDùng công cụ tạo video tích hợp sẵn của Muse (media.generate_video) "
            "với ảnh đã tải lên nếu có. Thực hiện tạo video thật và trả về video kết quả. "
            "Không chuyển sang Runway hay yêu cầu kết nối dịch vụ bên ngoài. "
            "Nếu công cụ tích hợp không khả dụng, báo đúng lỗi công cụ; không tự suy đoán cần Runway."
        )
    return f"{instruction}{aspect}{provider}\n\nMô tả nội dung:\n{task.prompt.strip()}"
