"""Sequential, checkpointed film generation; dependent shots never run in parallel."""
import asyncio
import os
import uuid
import copy
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from playwright.async_api import async_playwright

from core.film_project import film_prompt, validate_continuity, shot_reference_assets
from core.film_content import inspect_project, describe_issues
from core.film_genres import genre_instruction
from core.models import TaskItem, JobMode
from core.media_output import validate_output, build_generation_prompt
from utils.film_media import normalize_clip, extract_frame, assemble_film
from utils.file_utils import find_chromium_executable
from utils.proxy_utils import parse_proxy
from workers.automation_worker import AutomationWorker


def prepare_shot(store, index, source, stop=None):
    project = store.project
    shot = project.shots[index]
    validate_output(source, JobMode.TEXT_TO_VIDEO.value)
    shot.source_file = store.snapshot(source, "sources")
    store.save()  # A restart can finish this local stage without paying to generate again.
    prefix = store.root / "shots" / f"{index + 1:04d}_{shot.id}_take{shot.take:03d}"
    clip = normalize_clip(store.asset(shot.source_file), str(prefix) + ".mp4",
                          shot.timeline_seconds, (project.width, project.height), project.fps, stop)
    first = extract_frame(clip, str(prefix) + "_first.png", stop=stop)
    last = extract_frame(clip, str(prefix) + "_last.png", last=True, stop=stop)
    shot.clip, shot.first_frame, shot.last_frame = map(store.relative, (clip, first, last))
    shot.clip_sha256 = store.digest(clip)
    shot.last_frame_sha256 = store.digest(last)
    shot.status = "REVIEW" if project.review_required else "APPROVED"
    shot.approved_by = "" if project.review_required else "automatic"
    shot.error = ""
    project.export_file = ""
    project.state = "REVIEW" if project.review_required else "READY"
    store.save()


class FilmWorker(AutomationWorker):
    changed = pyqtSignal()
    message = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, store, profile, selectors, global_proxy="", review_config=None):
        super().__init__([], [profile], [], selectors, output_dir=str(store.root / "incoming"),
                         auto_new_chat=True, global_proxy=global_proxy)
        self.store = store
        self.current_shot = None
        self.current_reference = None
        self.submitted = False
        # Match batch Text -> Image/Video: never open an interactive window.
        # Expired sessions are reported in the app; login stays an explicit action.
        self.wait_for_login = False
        self.review_config = review_config or {}
        self.task_progress_signal.connect(lambda _, message: self.message.emit(message))

    def run(self):
        try:
            asyncio.run(self._render_film())
        except Exception as exc:
            if self.current_shot is not None and self.current_shot.status == "GENERATING":
                self.current_shot.status = "WAITING" if self.submitted or self._stop_requested else "FAILED"
                self.current_shot.error = str(exc)
            self.store.project.state = "WAITING" if self._stop_requested or self.submitted else "ERROR"
            self.store.save()
            self.failed.emit(str(exc))
        finally:
            self.changed.emit()

    async def _before_submit(self, page, task, prompt):
        self.submitted = True
        if self.current_reference is not None:
            self.current_reference.submitted_prompt = prompt
            self.current_reference.submission_url = page.url
            self.store.save()
            return
        shot = self.current_shot
        shot.submitted_prompt = prompt
        shot.submission_mode = task.mode
        shot.submission_url = page.url
        shot.input_refs = [self.store.snapshot(path, "used_refs") for path in task.references]
        shot.reference_audit = self._reference_roles(task)
        self.store.save()  # Written BEFORE clicking Send; restart cannot accidentally resubmit.

    def _reference_roles(self, task):
        selected = None if self.current_shot is None else set([*self.current_shot.character_ids, self.current_shot.location_id])
        known = {}
        for ref in self.store.project.references:
            if selected is None or ref.id in selected:
                for image in ref.images:
                    known.setdefault(str(Path(self.store.asset(image)).resolve()), []).append(ref)
        roles = []
        for index, path in enumerate(task.references):
            refs = known.get(str(Path(path).resolve()), [])
            kinds = {ref.kind for ref in refs}
            kind = (next(iter(kinds)) if len(kinds) == 1 else "reference") if refs else ("start_frame" if index == 0 and task.mode == JobMode.REFERENCE_IMAGE_TO_VIDEO.value else "style")
            for ref in refs:
                relative = self.store.relative(path)
                expected = ref.image_hashes.get(relative)
                if expected and self.store.digest(path) != expected:
                    raise ValueError(f"Ảnh chuẩn {ref.name} đã thay đổi; chưa gửi yêu cầu.")
            roles.append({"number": index + 1, "id": refs[0].id if refs else "", "ids": [ref.id for ref in refs], "kind": kind,
                          "name": " / ".join(ref.name for ref in refs) if refs else ("Khung bắt đầu video" if kind == "start_frame" else "Phong cách bổ sung"),
                          "image": self.store.relative(path), "sha256": self.store.digest(path)})
        return roles

    def _build_generation_prompt(self, task):
        roles = self._reference_roles(task)
        descriptions = []
        for ref in roles:
            purpose = {"character": "khóa nhận dạng nhân vật, không lấy nền của ảnh này",
                       "location": "khóa bố cục địa điểm và ánh sáng, không thay nhân vật",
                       "reference": "ảnh dùng chung cho các đối tượng nêu tên, giữ riêng vai trò nhân vật và bối cảnh",
                       "start_frame": "khung hình bắt đầu; tiếp diễn từ đúng bố cục này",
                       "style": "tham chiếu phong cách"}[ref["kind"]]
            descriptions.append(f"Ảnh {ref['number']}: {ref['name']} — {purpose}.")
        prepared = copy.copy(task)
        if descriptions:
            prepared.prompt += "\nVai trò các ảnh đã tải theo đúng thứ tự:\n" + "\n".join(descriptions)
        return build_generation_prompt(prepared)

    async def _after_submit(self, page, task, prompt):
        if self.current_reference is not None:
            self.current_reference.submission_url = page.url
            self.store.save()
            return
        self.current_shot.submission_url = page.url
        self.store.save()

    async def _ensure_canonical_references(self, context, profile):
        used = {key for shot in self.store.project.shots for key in [*shot.character_ids, shot.location_id] if key}
        # Check every existing used asset before paying to generate missing ones.
        for ref in self.store.project.references:
            if ref.id in used:
                for image in ref.images:
                    path = self.store.asset(image)
                    validate_output(path, JobMode.TEXT_TO_IMAGE.value)
                    if ref.image_hashes.get(image) and self.store.digest(path) != ref.image_hashes[image]:
                        raise ValueError(f"Ảnh chuẩn {ref.name} đã thay đổi bên ngoài dự án. Nhập lại ảnh.")
        for ref in self.store.project.references:
            if ref.id not in used:
                continue
            if ref.images:
                for image in ref.images:
                    validate_output(self.store.asset(image), JobMode.TEXT_TO_IMAGE.value)
                continue
            if ref.generation_status in ("FAILED", "WAITING") and not ref.submitted_prompt:
                # A login/load failure before Send is safe to retry. Do not
                # replay the stale error after the user restored their session.
                ref.generation_status, ref.error = "PENDING", ""
                self.store.save()
            if ref.generation_status != "PENDING":
                raise ValueError(f"Ảnh chuẩn {ref.name} cần kiểm tra: {ref.error or 'nhập ảnh đã có từ Muse để tránh gửi trùng.'}")
            if self._stop_requested:
                raise InterruptedError("Đã dừng trước khi tạo ảnh chuẩn.")
            self.current_reference = ref
            self.submitted = False
            ref.generation_status = "GENERATING"
            self.store.save()
            self.message.emit(f"Chuẩn bị ảnh {'nhân vật' if ref.kind == 'character' else 'bối cảnh'}: {ref.name}")
            prompt = (f"Tạo ảnh chuẩn duy nhất cho {'nhân vật' if ref.kind == 'character' else 'bối cảnh'} {ref.name}. "
                      f"{ref.description}. Phong cách chung: {self.store.project.continuity_notes}. "
                      + genre_instruction(self.store.project.genre, stage="reference") + "\n"
                      + ("Chỉ nhân vật này, toàn thân, nền đơn giản, ánh sáng rõ, không chữ, không collage."
                         if ref.kind == "character" else "Toàn cảnh địa điểm, giữ bố cục và ánh sáng rõ, không thêm nhân vật, không chữ."))
            task = TaskItem(f"ref_{ref.id}", prompt, mode=JobMode.TEXT_TO_IMAGE.value,
                            aspect_ratio=self.store.project.aspect)
            try:
                ok, error, output = await self._execute_validated_phase(context, task, profile, 0)
                if not ok:
                    raise ValueError(error)
                image = self.store.snapshot(output, "canonical")
                ref.images = [image]
                ref.image_hashes = {image: self.store.digest(self.store.asset(image))}
                ref.generation_status, ref.error = "READY", ""
                self.store.save()
                self.changed.emit()
            except Exception as exc:
                ref.generation_status = "WAITING" if self.submitted else "FAILED"
                ref.error = str(exc)
                self.store.save()
                raise
            finally:
                self.current_reference = None
        self.submitted = False

    async def _render_film(self):
        project = self.store.project
        validate_continuity(project)
        issues = inspect_project(project)
        if issues:
            raise ValueError(describe_issues(issues))
        profile = self.profiles[0]
        for image in [project.seed_image, *project.anchor_images]:
            if image:
                validate_output(self.store.asset(image), JobMode.TEXT_TO_IMAGE.value)
        context = None
        try:
            self._playwright = await async_playwright().start()
            options = {"user_data_dir": os.path.abspath(profile.path), "headless": self.headless,
                       "viewport": {"width": 1366, "height": 768},
                       "executable_path": find_chromium_executable(headless=self.headless),
                       "args": ["--no-first-run", "--disable-blink-features=AutomationControlled"]}
            proxy = (profile.proxy or self.global_proxy).strip()
            if proxy:
                parsed = parse_proxy(proxy)
                if not parsed:
                    raise ValueError("Proxy của tài khoản không hợp lệ.")
                options["proxy"] = parsed
            context = await self._playwright.chromium.launch_persistent_context(**options)
            self._active_contexts = [context]
            await self._ensure_canonical_references(context, profile)
            for index, shot in enumerate(project.shots):
                if self._stop_requested:
                    break
                self.current_shot = shot
                self.submitted = False
                if shot.status == "APPROVED":
                    self.store.check_integrity(shot)
                    validate_output(self.store.asset(shot.clip), JobMode.TEXT_TO_VIDEO.value)
                    validate_output(self.store.asset(shot.last_frame), JobMode.TEXT_TO_IMAGE.value)
                    continue
                if shot.status == "REVIEW":
                    project.state = "REVIEW"
                    break
                if shot.status in ("WAITING", "GENERATING", "FAILED"):
                    if shot.source_file and not shot.clip:
                        self.message.emit(f"Hoàn thiện clip #{index + 1} đã tải; không gửi lại Muse")
                        await self._prepare_and_review(index, self.store.asset(shot.source_file))
                        self.changed.emit()
                        if project.review_required or shot.status == "REVIEW":
                            break
                        continue
                    project.state = "WAITING"
                    self.message.emit(f"Clip #{index + 1} đang dở. Nhập kết quả có sẵn hoặc chọn tạo lại; app không tự gửi trùng.")
                    break
                references, shot.reference_audit = shot_reference_assets(self.store, shot)
                references.extend(self.store.asset(path) for path in project.anchor_images)
                references = list(dict.fromkeys(references))
                if shot.continuation:
                    if index == 0 or project.shots[index - 1].status != "APPROVED":
                        raise ValueError("Phải duyệt clip trước khi tạo clip tiếp nối.")
                    previous = project.shots[index - 1]
                    validate_output(self.store.asset(previous.last_frame), JobMode.TEXT_TO_IMAGE.value)
                    references.insert(0, self.store.asset(previous.last_frame))
                    mode = JobMode.REFERENCE_IMAGE_TO_VIDEO.value
                elif index == 0 and project.seed_image:
                    references.insert(0, self.store.asset(project.seed_image))
                    mode = JobMode.REFERENCE_IMAGE_TO_VIDEO.value
                else:
                    mode = JobMode.TEXT_TO_IMAGE_TO_VIDEO.value
                shot.take += 1
                shot.status, project.state = "GENERATING", "GENERATING"
                shot.error = ""
                shot.input_refs = [self.store.relative(path) for path in references]
                self.store.save()
                self.changed.emit()
                self.message.emit(f"Clip {index + 1}/{len(project.shots)} · cảnh lớn {shot.sequence}")
                task = TaskItem(shot.id, film_prompt(project, shot), mode=mode, aspect_ratio=project.aspect,
                                video_duration=shot.request_seconds, references=references)
                success, error, output = await self._execute_task_on_profile(context, task, profile, index + 1)
                if not success:
                    shot.status = "WAITING" if self._stop_requested or error.startswith("WAITING:") else "FAILED"
                    shot.error = error.removeprefix("WAITING:").strip()
                    project.state = shot.status
                    self.store.save()
                    self.message.emit(shot.error)
                    break
                await self._prepare_and_review(index, output)
                self.changed.emit()
                if project.review_required or shot.status == "REVIEW":
                    break
            else:
                project.state = "READY_TO_EXPORT"
            if self._stop_requested:
                project.state = "STOPPED"
            self.store.save()
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
            self._active_contexts = []

    async def _prepare_and_review(self, index, source):
        project = self.store.project
        shot = project.shots[index]
        await asyncio.to_thread(prepare_shot, self.store, index, source, lambda: self._stop_requested)
        if not project.visual_review_enabled:
            return
        from core.film_visual_review import review_shot
        self.message.emit(f"Gemini đang đối chiếu ảnh chuẩn và đầu/cuối clip {index + 1}…")
        try:
            if self._stop_requested:
                raise InterruptedError()
            shot.visual_review = await asyncio.to_thread(review_shot, self.store, shot, self.review_config)
            if shot.visual_review["verdict"] != "pass":
                shot.status, shot.approved_by = "REVIEW", ""
                shot.error = "Cần xem lại: " + shot.visual_review["summary"]
        except Exception:
            shot.status, shot.approved_by = "REVIEW", ""
            shot.error = "Chưa đối chiếu được hình ảnh bằng Gemini. Xem ảnh chuẩn và khung đầu/cuối trước khi duyệt."
        if shot.status == "REVIEW":
            project.state = "REVIEW"
        self.store.save()


class FilmImportWorker(QThread):
    changed = pyqtSignal()
    message = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, store, index, source):
        super().__init__()
        self.store, self.index, self.source = store, index, source
        self.stopped = False

    def stop(self):
        self.stopped = True

    def run(self):
        shot = self.store.project.shots[self.index]
        try:
            shot.take += 1
            shot.status = "GENERATING"
            self.store.save()
            self.message.emit("Đang chuẩn hóa clip có sẵn và trích khung hình đầu/cuối")
            prepare_shot(self.store, self.index, self.source, lambda: self.stopped)
        except Exception as exc:
            shot.status = "WAITING" if self.stopped else "FAILED"
            shot.error = str(exc)
            self.store.save()
            self.failed.emit(str(exc))
        finally:
            self.changed.emit()


class FilmExportWorker(QThread):
    changed = pyqtSignal()
    message = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, store, music="", narration="", keep_clip_audio=True):
        super().__init__()
        self.store, self.music, self.narration, self.keep_clip_audio = store, music, narration, keep_clip_audio
        self.stopped = False

    def stop(self):
        self.stopped = True

    def run(self):
        try:
            path = self.store.root / "exports" / f"film_{uuid.uuid4().hex[:10]}.mp4"
            result = assemble_film(self.store, path, self.music, self.narration, self.keep_clip_audio,
                                   lambda: self.stopped, lambda _, text: self.message.emit(text))
            if self.store.project.export_file:
                self.store.project.export_history.append(self.store.project.export_file)
            self.store.project.export_file = self.store.relative(result)
            self.store.project.state = "EXPORTED"
            self.store.save()
            self.message.emit(f"Đã xuất phim: {result}")
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.changed.emit()
