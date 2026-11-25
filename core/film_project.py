"""Persistent storyboard, approvals and dependencies for long-form video projects."""
import hashlib
import json
import math
import os
import shutil
import tempfile
import uuid
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class FilmShot:
    id: str
    prompt: str
    sequence: int
    continuation: bool
    timeline_seconds: float
    request_seconds: int
    status: str = "PENDING"
    take: int = 0
    source_file: str = ""
    clip: str = ""
    first_frame: str = ""
    last_frame: str = ""
    input_refs: list[str] = field(default_factory=list)
    approved_by: str = ""
    error: str = ""

    submission_url: str = ""
    submitted_prompt: str = ""
    submission_mode: str = ""
    history: list[dict] = field(default_factory=list)
    clip_sha256: str = ""
    last_frame_sha256: str = ""
    character_ids: list[str] = field(default_factory=list)
    location_id: str = ""
    start_state: str = ""
    end_state: str = ""
    reference_audit: list[dict] = field(default_factory=list)
    visual_review: dict = field(default_factory=dict)


@dataclass
class FilmReference:
    id: str
    kind: str
    name: str
    description: str
    images: list[str] = field(default_factory=list)
    image_hashes: dict[str, str] = field(default_factory=dict)
    generation_status: str = "PENDING"
    submitted_prompt: str = ""
    submission_url: str = ""
    error: str = ""
    history: list[dict] = field(default_factory=list)


@dataclass
class FilmProject:
    title: str
    target_seconds: int
    clip_seconds: int
    aspect: str
    profile_id: str
    continuity_notes: str
    shots: list[FilmShot]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    format_version: int = 2
    review_required: bool = True
    seed_image: str = ""
    anchor_images: list[str] = field(default_factory=list)
    width: int = 1280
    height: int = 720
    fps: int = 24
    export_file: str = ""
    export_history: list[str] = field(default_factory=list)
    music_file: str = ""
    narration_file: str = ""
    keep_clip_audio: bool = True
    state: str = "DRAFT"
    references: list[FilmReference] = field(default_factory=list)
    visual_review_enabled: bool = False
    genre: str = ""
    production_skills: dict = field(default_factory=dict)

    @property
    def ready_to_export(self):
        return bool(self.shots) and all(shot.status == "APPROVED" for shot in self.shots)


def plan_film(title, paragraphs, target_seconds=600, clip_seconds=10, aspect="16:9",
              profile_id="", continuity_notes=""):
    paragraphs = [text.strip() for text in paragraphs if text.strip()]
    if not paragraphs:
        raise ValueError("Nhập kịch bản: mỗi đoạn cách nhau một dòng trống là một cảnh lớn.")
    if not 1 <= target_seconds <= 7200 or clip_seconds not in (5, 10):
        raise ValueError("Thời lượng phim phải từ 1 giây đến 120 phút; mỗi clip 5 hoặc 10 giây.")
    sizes = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (720, 720)}
    if aspect not in sizes:
        raise ValueError("Chọn khung hình 16:9, 9:16 hoặc 1:1.")
    count = math.ceil(target_seconds / clip_seconds)
    if len(paragraphs) > count:
        raise ValueError(f"Có {len(paragraphs)} cảnh nhưng thời lượng chỉ đủ {count} clip. Tăng thời lượng hoặc giảm số cảnh.")
    base, extra = divmod(count, len(paragraphs))
    remaining = target_seconds
    shots = []
    for sequence, prompt in enumerate(paragraphs, 1):
        for part in range(base + (sequence <= extra)):
            duration = min(remaining, clip_seconds)
            shots.append(FilmShot(uuid.uuid4().hex[:12], prompt, sequence, part > 0, duration, clip_seconds))
            remaining -= duration
    width, height = sizes[aspect]
    return FilmProject(title.strip() or "Phim mới", target_seconds, clip_seconds, aspect,
                       profile_id, continuity_notes.strip(), shots, width=width, height=height)


class FilmStore:
    def __init__(self, manifest, project):
        self.manifest = Path(manifest).resolve()
        self.root = self.manifest.parent
        self.project = project

    def asset(self, relative):
        if not relative or Path(relative).is_absolute():
            raise ValueError("Đường dẫn tài sản dự án không hợp lệ.")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Tài sản phải nằm trong thư mục dự án.")
        return str(path)

    def relative(self, path):
        return Path(path).resolve().relative_to(self.root).as_posix()

    @staticmethod
    def digest(path):
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def check_integrity(self, shot):
        for relative, expected in [(shot.clip, shot.clip_sha256), (shot.last_frame, shot.last_frame_sha256)]:
            if expected and self.digest(self.asset(relative)) != expected:
                raise ValueError("Clip hoặc khung hình đã thay đổi bên ngoài dự án. Nhập lại và duyệt lại trước khi tiếp nối.")

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        if self.manifest.exists() and self.project.format_version == 1:
            backup = self.manifest.with_name(self.manifest.stem + ".v1.backup.json")
            if not backup.exists():
                shutil.copyfile(self.manifest, backup)
        self.project.format_version = 2
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=self.root, suffix=".tmp", encoding="utf-8", delete=False) as stream:
                temporary = stream.name
                json.dump(asdict(self.project), stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.manifest)
        finally:
            if temporary and os.path.exists(temporary):
                os.remove(temporary)

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("format_version") not in (1, 2):
            raise ValueError("Phiên bản dự án không được hỗ trợ.")
        shot_fields = {item.name for item in fields(FilmShot)}
        shots = [FilmShot(**{key: value for key, value in shot.items() if key in shot_fields}) for shot in data.pop("shots")]
        references = [FilmReference(**item) for item in data.pop("references", [])]
        project = FilmProject(**data, shots=shots, references=references)
        validate_continuity(project)
        if not 1 <= project.target_seconds <= 7200 or project.clip_seconds not in (5, 10):
            raise ValueError("Thời lượng dự án không hợp lệ.")
        if any(value <= 0 or value % 2 for value in [project.width, project.height]) or max(project.width, project.height) > 4096 or not 1 <= project.fps <= 60:
            raise ValueError("Chuẩn hình/FPS của dự án không hợp lệ.")
        if not shots or len({shot.id for shot in shots}) != len(shots):
            raise ValueError("Danh sách clip dự án không hợp lệ.")
        if abs(sum(shot.timeline_seconds for shot in shots) - project.target_seconds) > 0.001:
            raise ValueError("Tổng thời lượng storyboard không khớp thời lượng phim.")
        store = cls(path, project)
        # A process may have submitted a paid generation before it stopped.
        # Never automatically submit that shot again on reopening the project.
        interrupted = False
        for shot in shots:
            if type(shot.continuation) is not bool or not isinstance(shot.prompt, str) or not shot.prompt.strip():
                raise ValueError("Nội dung hoặc cách nối clip không hợp lệ.")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", shot.id):
                raise ValueError("Mã clip trong dự án không hợp lệ.")
            if shot.status not in {"PENDING", "GENERATING", "WAITING", "REVIEW", "APPROVED", "FAILED"} or not 0 < shot.timeline_seconds <= project.clip_seconds or shot.request_seconds not in (5, 10):
                raise ValueError("Trạng thái/thời lượng clip không hợp lệ.")
            for value in [shot.clip, shot.first_frame, shot.last_frame, shot.source_file, *shot.input_refs]:
                if value:
                    store.asset(value)
            if shot.status == "GENERATING":
                shot.status = "WAITING"
                shot.error = "Tác vụ trước bị gián đoạn. Kiểm tra Muse và nhập clip có sẵn, hoặc chủ động tạo lại."
                interrupted = True
        for value in [project.seed_image, project.export_file, project.music_file, project.narration_file,
                      *project.export_history, *project.anchor_images]:
            if value:
                store.asset(value)
        for reference in project.references:
            for value in reference.images:
                store.asset(value)
            if reference.generation_status == "GENERATING":
                reference.generation_status = "WAITING"
                reference.error = "Ảnh chuẩn đã gửi trước khi app dừng. Kiểm tra Muse hoặc nhập ảnh đã tạo."
                interrupted = True
        if interrupted:
            project.state = "WAITING"
            store.save()
        return store

    def snapshot(self, source, folder="refs"):
        source = Path(source).resolve()
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        target = self.root / folder / (digest.hexdigest()[:20] + source.suffix.lower())
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        return self.relative(target)

    def invalidate_from(self, index):
        affected = []
        for offset in range(index, len(self.project.shots)):
            shot = self.project.shots[offset]
            if offset > index and not shot.continuation:
                break
            if shot.clip or shot.source_file:
                shot.history.append({key: getattr(shot, key) for key in
                                     ("take", "prompt", "source_file", "clip", "first_frame", "last_frame", "input_refs", "approved_by", "clip_sha256", "last_frame_sha256", "submitted_prompt", "submission_url", "submission_mode", "reference_audit", "visual_review", "character_ids", "location_id", "start_state", "end_state")})
            for key in ("clip", "source_file", "first_frame", "last_frame", "approved_by", "error",
                        "submission_url", "submitted_prompt", "submission_mode", "clip_sha256", "last_frame_sha256"):
                setattr(shot, key, "")
            shot.input_refs = []
            shot.reference_audit = []
            shot.visual_review = {}
            shot.status = "PENDING"
            affected.append(offset)
        self.project.export_file = ""
        self.project.state = "DRAFT"
        self.save()
        return affected


def film_prompt(project, shot):
    from core.film_genres import genre_instruction
    from core.film_skills import skill_instruction
    lock = f"Quy tắc xuyên suốt: {project.continuity_notes}\n" if project.continuity_notes else ""
    lock += genre_instruction(project.genre, stage="video") + "\n" if project.genre else ""
    lock += skill_instruction('video') + "\n"
    if shot.continuation:
        direction = (
            "Ảnh tham chiếu đầu tiên là KHUNG HÌNH CUỐI của clip ngay trước. "
            "Dùng chính ảnh này làm khung hình bắt đầu. Tiếp diễn hành động từ vị trí hiện tại, "
            "giữ nguyên nhân vật, trang phục, ánh sáng, hướng chuyển động và hướng máy. "
            "Một cú máy liên tục, không mở lại từ đầu cảnh. Các ảnh còn lại chỉ khóa nhận dạng/phong cách."
        )
    else:
        direction = "Bắt đầu cảnh mới. Giữ nhận dạng và phong cách theo ảnh tham chiếu và quy tắc xuyên suốt."
    identities = []
    for reference in project.references:
        if reference.id in shot.character_ids or reference.id == shot.location_id:
            role = "Nhân vật" if reference.kind == "character" else "Bối cảnh"
            identities.append(f"{role} [{reference.id}] {reference.name}: {reference.description}")
    state = f"\nTrạng thái đầu clip: {shot.start_state}" if shot.start_state else ""
    if shot.end_state:
        state += f"\nTrạng thái kết thúc cần đạt: {shot.end_state}"
    roles = "\n".join(identities)
    return f"{lock}{direction}\n{roles}{state}\nHành động/câu chuyện của cảnh này: {shot.prompt}"


def validate_continuity(project):
    references = {ref.id: ref for ref in project.references}
    if len(references) != len(project.references):
        raise ValueError("Mã nhân vật/bối cảnh bị trùng.")
    for ref in project.references:
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", ref.id) or ref.kind not in ("character", "location")
                or not ref.name.strip() or not ref.description.strip()):
            raise ValueError("Hồ sơ tham chiếu cần mã, tên và mô tả hợp lệ.")
    for index, shot in enumerate(project.shots):
        if len(shot.character_ids) != len(set(shot.character_ids)):
            raise ValueError(f"Clip {index + 1}: nhân vật bị gắn trùng.")
        for key in shot.character_ids:
            if key not in references or references[key].kind != "character":
                raise ValueError(f"Clip {index + 1}: nhân vật tham chiếu không tồn tại.")
        if shot.location_id and (shot.location_id not in references or references[shot.location_id].kind != "location"):
            raise ValueError(f"Clip {index + 1}: bối cảnh không tồn tại.")
        if shot.continuation:
            if index == 0:
                raise ValueError("Clip đầu tiên phải bắt đầu cảnh mới.")
            previous = project.shots[index - 1]
            if shot.location_id != previous.location_id or shot.sequence != previous.sequence:
                raise ValueError(f"Clip {index + 1}: đổi bối cảnh phải chọn Cảnh mới.")
            if previous.end_state and shot.start_state and previous.end_state.strip() != shot.start_state.strip():
                raise ValueError(f"Clip {index + 1}: trạng thái đầu không khớp kết thúc clip trước.")


def shot_reference_assets(store, shot):
    """Resolve only this shot's canonical assets; never infer refs from names."""
    selected = {key for key in [*shot.character_ids, shot.location_id] if key}
    files, audit = [], []
    for ref in store.project.references:
        if ref.id not in selected:
            continue
        if not ref.images:
            raise ValueError(f"Chưa có ảnh chuẩn: {ref.name}.")
        for image in ref.images:
            path = store.asset(image)
            digest = store.digest(path)
            expected = ref.image_hashes.get(image)
            if expected and expected != digest:
                raise ValueError(f"Ảnh chuẩn {ref.name} đã thay đổi bên ngoài dự án. Nhập lại ảnh trước khi chạy.")
            files.append(path)
            audit.append({"id": ref.id, "kind": ref.kind, "name": ref.name, "image": image, "sha256": digest})
    return files, audit
