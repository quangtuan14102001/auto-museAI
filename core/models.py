from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class TaskStatus(str, Enum):
    READY = "READY"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    WAITING = "WAITING"
    OK = "OK"
    FAIL = "FAIL"


class JobMode(str, Enum):
    TEXT_TO_IMAGE = "TEXT -> IMAGE"
    TEXT_TO_VIDEO = "TEXT -> VIDEO"
    REFERENCE_IMAGE_TO_VIDEO = "REFERENCE IMAGE -> VIDEO"
    TEXT_TO_IMAGE_TO_VIDEO = "TEXT -> IMAGE -> VIDEO"


@dataclass
class ProfileItem:
    id: str
    name: str
    path: str
    enabled: bool = True
    status: str = "Sẵn sàng"
    tasks_done: int = 0
    tasks_total: int = 0
    proxy: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "enabled": self.enabled,
            "status": self.status,
            "tasks_done": self.tasks_done,
            "tasks_total": self.tasks_total,
            "proxy": self.proxy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProfileItem":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            path=data.get("path", ""),
            enabled=data.get("enabled", True),
            status=data.get("status", "Sẵn sàng"),
            tasks_done=data.get("tasks_done", 0),
            tasks_total=data.get("tasks_total", 0),
            proxy=data.get("proxy", ""),
        )


@dataclass
class AliasItem:
    tag: str
    name: str
    file_path: str

    def to_dict(self) -> dict:
        return {
            "tag": self.tag,
            "name": self.name,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AliasItem":
        tag = data.get("tag", "").strip()
        if tag and not tag.startswith("@"):
            tag = f"@{tag}"
        return cls(
            tag=tag,
            name=data.get("name", ""),
            file_path=data.get("file_path", ""),
        )


@dataclass
class TaskItem:
    id: str
    prompt: str
    mode: str = JobMode.TEXT_TO_VIDEO.value
    aspect_ratio: str = "16:9"
    video_duration: int = 5
    status: str = TaskStatus.READY.value
    profile_assigned: str = ""
    output_file: str = ""
    error_message: str = ""
    created_at: str = ""
    retry_count: int = 0
    references: List[str] = field(default_factory=list)
    generated_image_file: str = ""
    progress_message: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "mode": self.mode,
            "aspect_ratio": self.aspect_ratio,
            "video_duration": self.video_duration,
            "status": self.status,
            "profile_assigned": self.profile_assigned,
            "output_file": self.output_file,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "retry_count": self.retry_count,
            "references": self.references,
            "generated_image_file": self.generated_image_file,
            "progress_message": self.progress_message if self.status == TaskStatus.WAITING.value else "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskItem":
        return cls(
            id=data.get("id", ""),
            prompt=data.get("prompt", ""),
            mode=data.get("mode", JobMode.TEXT_TO_VIDEO.value),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
            video_duration=data.get("video_duration", 5),
            status=data.get("status", TaskStatus.READY.value),
            profile_assigned=data.get("profile_assigned", ""),
            output_file=data.get("output_file", ""),
            error_message=data.get("error_message", ""),
            created_at=data.get("created_at", ""),
            retry_count=data.get("retry_count", 0),
            references=data.get("references", []),
            generated_image_file=data.get("generated_image_file", ""),
            progress_message=data.get("progress_message", ""),
        )
