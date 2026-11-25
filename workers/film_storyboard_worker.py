"""Structured per-shot story and canonical reference planning."""
import json
import math
import copy
import os
from pathlib import Path
from PyQt6.QtCore import pyqtSignal
from workers.llm_rewriter import LLMRewriterWorker
from core.film_project import plan_film, FilmReference, validate_continuity
from core.film_genres import genre_instruction, FILM_CONTENT_GUIDANCE
from core.film_skills import skill_instruction
from core.storyboard_json import decode_storyboard_json, InvalidStoryboardJSON
from core.film_content import inspect_project, describe_issues


def normalize_location_cuts(data, start=0):
    """Only fix unambiguous AI metadata: a different location is a cut.

    Never rewrite actions/states or an already checkpointed prefix. A following
    continuation inherits the newly cut sequence until the next explicit cut.
    """
    result = copy.deepcopy(data)
    rows = result.get("shots", []) if isinstance(result, dict) else []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return result, 0
    next_sequence = max((r.get("sequence", 0) for r in rows if type(r.get("sequence")) is int), default=0) + 1
    fixes = 0
    if start == 0 and rows and rows[0].get("continuation") is True:
        rows[0]["continuation"] = False
        fixes += 1
    for i in range(max(1, start), len(rows)):
        row, previous = rows[i], rows[i - 1]
        if row.get("continuation") is not True:
            continue
        if (isinstance(row.get("location_id"), str) and row["location_id"]
                and isinstance(previous.get("location_id"), str) and previous["location_id"]
                and row["location_id"] != previous["location_id"]):
            row["continuation"] = False
            row["sequence"] = next_sequence
            next_sequence += 1
            fixes += 1
        elif (row.get("location_id") == previous.get("location_id")
              and type(row.get("sequence")) is int and type(previous.get("sequence")) is int
              and row["sequence"] != previous["sequence"]):
            row["sequence"] = previous.get("sequence")
            fixes += 1
    return result, fixes


def link_continuation_states(data, start=0):
    """Derive an AI continuation's incoming state from its predecessor.

    The same boundary used to be generated as two independent free-text fields,
    then compared literally. Keep one source of truth for that boundary. Only
    newly generated rows are linked; approved projects/runtime remain strict.
    Actions, outgoing states, references and existing checkpoints are untouched.
    """
    result = copy.deepcopy(data)
    rows = result.get("shots", []) if isinstance(result, dict) else []
    fixes = 0
    if not isinstance(rows, list):
        return result, fixes
    for i in range(max(1, start), len(rows)):
        row, previous = rows[i], rows[i - 1]
        if not isinstance(row, dict) or not isinstance(previous, dict):
            continue
        incoming = previous.get("end_state")
        if (row.get("continuation") is True and row.get("location_id") == previous.get("location_id")
                and row.get("sequence") == previous.get("sequence")
                and isinstance(incoming, str) and incoming.strip()
                and isinstance(row.get("start_state"), str) and row["start_state"].strip()
                and row["start_state"] != incoming):
            row["start_state"] = incoming
            fixes += 1
    return result, fixes


def apply_storyboard(data, title, seconds, clip_seconds, aspect, profile_id, notes):
    if not isinstance(data, dict) or not isinstance(data.get("shots"), list):
        raise ValueError("AI chưa trả về storyboard có cấu trúc hợp lệ.")
    rows = data["shots"]
    count = math.ceil(seconds / clip_seconds)
    if len(rows) != count:
        raise ValueError(f"AI trả {len(rows)} clip, cần đúng {count} clip.")
    refs = []
    for kind, key in [("character", "characters"), ("location", "locations")]:
        values = data.get(key)
        if not isinstance(values, list):
            raise ValueError("Thiếu danh sách nhân vật/bối cảnh.")
        for item in values:
            if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip()
                                                 for k in ("id", "name", "description")):
                raise ValueError("Hồ sơ nhân vật/bối cảnh thiếu thông tin.")
            refs.append(FilmReference(item["id"], kind, item["name"], item["description"]))
    actions = []
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("action"), str) or not row["action"].strip()
                or type(row.get("sequence")) is not int or row["sequence"] < 1
                or type(row.get("continuation")) is not bool
                or not isinstance(row.get("character_ids"), list)
                or any(not isinstance(key, str) for key in row["character_ids"])
                or not isinstance(row.get("location_id"), str)
                or any(not isinstance(row.get(key), str) or not row[key].strip() for key in ("start_state", "end_state"))):
            raise ValueError("Một clip thiếu hành động, nhân vật hoặc trạng thái đầu/cuối.")
        actions.append(row["action"].strip())
    if len(set(action.casefold() for action in actions)) != len(actions):
        raise ValueError("AI lặp nguyên hành động giữa các clip. Cần tạo lại storyboard.")
    project = plan_film(title, actions, seconds, clip_seconds, aspect, profile_id, notes)
    project.references = refs
    for shot, row in zip(project.shots, rows):
        for key in ("sequence", "continuation", "character_ids", "location_id", "start_state", "end_state"):
            setattr(shot, key, row[key])
    validate_continuity(project)
    return project


class FilmStoryboardWorker(LLMRewriterWorker):
    storyboard_ready = pyqtSignal(object)
    partial_ready = pyqtSignal(object)
    progress = pyqtSignal(str)

    def __init__(self, idea, seconds, clip_seconds, notes, provider, api_key, model_name,
                 existing=None, checkpoint_path=None, genre=""):
        super().__init__(idea, math.ceil(seconds / clip_seconds), [], provider, api_key, model_name)
        self.seconds, self.clip_seconds, self.notes = seconds, clip_seconds, notes
        self.request_timeout = 180
        self.max_output_tokens = 8192
        self.existing = copy.deepcopy(existing)
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self.genre = genre
        self.last_invalid_json = ""
        reference = {"type": "OBJECT", "properties": {key: {"type": "STRING"} for key in ("id", "name", "description")},
                     "required": ["id", "name", "description"]}
        shot = {"type": "OBJECT", "properties": {
            "action": {"type": "STRING"}, "sequence": {"type": "INTEGER"}, "continuation": {"type": "BOOLEAN"},
            "character_ids": {"type": "ARRAY", "items": {"type": "STRING"}}, "location_id": {"type": "STRING"},
            "start_state": {"type": "STRING"}, "end_state": {"type": "STRING"}},
            "required": ["action", "sequence", "continuation", "character_ids", "location_id", "start_state", "end_state"]}
        self.structured_schema = {"type": "OBJECT", "properties": {
            "characters": {"type": "ARRAY", "items": reference}, "locations": {"type": "ARRAY", "items": reference},
            "shots": {"type": "ARRAY", "items": shot}}, "required": ["characters", "locations", "shots"]}

    def _validate_partial(self, data):
        count = len(data.get("shots", [])) if isinstance(data, dict) else 0
        if not 0 < count <= self.num_scenes:
            raise ValueError("Số clip AI trả về không hợp lệ hoặc vượt thời lượng đã chọn.")
        apply_storyboard(data, "Kiểm tra", count * self.clip_seconds, self.clip_seconds, "16:9", "", self.notes)

    def _checkpoint(self, data):
        if self.checkpoint_path:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.checkpoint_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.checkpoint_path)
        if len(data["shots"]) < self.num_scenes:
            self.partial_ready.emit(copy.deepcopy(data))

    def _append(self, data, extra):
        if not isinstance(extra, dict) or not isinstance(extra.get("shots"), list) or not extra["shots"]:
            raise ValueError("Phần bổ sung chưa có clip mới.")
        if len(extra["shots"]) > self.num_scenes - len(data["shots"]):
            raise ValueError("Phần bổ sung vượt số clip còn thiếu.")
        merged = copy.deepcopy(data)
        # Existing canonical definitions are immutable during continuation.
        known = {item["id"] for key in ("characters", "locations") for item in merged[key]}
        for key in ("characters", "locations"):
            additions = extra.get(key, [])
            if not isinstance(additions, list):
                raise ValueError("Danh sách tham chiếu bổ sung không hợp lệ.")
            for item in additions:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    raise ValueError("Tham chiếu bổ sung thiếu ID.")
                if item["id"] not in known:
                    merged[key].append(item)
                    known.add(item["id"])
        merged["shots"].extend(copy.deepcopy(extra["shots"]))
        merged, fixes = normalize_location_cuts(merged, len(data["shots"]))
        merged, linked = link_continuation_states(merged, len(data["shots"]))
        if linked:
            self.progress.emit(f"Đã liên kết {linked} trạng thái nối cảnh từ kết thúc clip trước.")
        if fixes:
            self.progress.emit(f"Đã chuẩn hóa {fixes} đánh dấu cảnh/nối cảnh theo bối cảnh.")
        self._validate_partial(merged)
        return merged

    def _extract_json_array(self, text):
        try:
            return decode_storyboard_json(text)
        except InvalidStoryboardJSON:
            self.last_invalid_json = text
            if self.checkpoint_path:
                try:
                    self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                    self.checkpoint_path.with_suffix(".invalid.txt").write_text(text, encoding="utf-8")
                except OSError:
                    pass
            raise

    def _call_with_json_repair(self, instruction):
        call = {"gemini": self._call_gemini, "openai": self._call_openai,
                "anthropic": self._call_anthropic, "muse": getattr(self, "_call_muse", None)}[self.provider]
        try:
            return call(instruction)
        except InvalidStoryboardJSON:
            self.progress.emit("AI trả sai định dạng. Đang yêu cầu sửa cấu trúc kịch bản…")
            return call(instruction + "\nCHỈ SỬA CÚ PHÁP JSON của kết quả dưới đây. Giữ nội dung, ID và thứ tự; "
                        "không thêm markdown, dùng dấu nháy kép đúng và đóng đủ ngoặc.\n" + self.last_invalid_json)

    def run(self):
        if (self.provider != "muse" and not self.api_key) or self.provider not in ("gemini", "openai", "anthropic", "muse"):
            self.error_signal.emit("Cấu hình API key AI trước khi lập storyboard.")
            return
        instruction = (
            f"Lập phim {self.seconds} giây gồm đúng {self.num_scenes} clip, mỗi clip {self.clip_seconds} giây "
            "(clip cuối sẽ được cắt nếu dư). Viết hành động riêng biệt cho từng clip, có mở đầu, diễn biến, kết thúc. "
            + FILM_CONTENT_GUIDANCE +
            f"{genre_instruction(self.genre)} {skill_instruction('storyboard')} Quy tắc: {self.notes}. Trả duy nhất JSON object theo mẫu: "
            '{"characters":[{"id":"robot","name":"Rô","description":"ngoại hình, quần áo, màu sắc cố định"}],'
            '"locations":[{"id":"forest","name":"Khu rừng","description":"bố cục, vật mốc, ánh sáng cố định"}],'
            '"shots":[{"action":"Hành động và chuyển động máy riêng của clip", "sequence":1,'
            '"continuation":false,"character_ids":["robot"],"location_id":"forest",'
            '"start_state":"Vị trí, hướng nhìn, đồ vật đang cầm", "end_state":"Trạng thái sau hành động"}]}.'
            " Mọi ID phải tồn tại trong characters/locations, chỉ gắn nhân vật thực sự xuất hiện. "
            "Clip đầu continuation=false. Nối liên tục dùng cùng sequence và location_id; "
            "start_state phải sao chép NGUYÊN VĂN end_state clip trước. "
            "Với continuation=true, app lấy trạng thái đầu từ end_state clip trước làm nguồn duy nhất; "
            "hãy viết action có thể thực hiện từ chính trạng thái đó, không nhảy thời gian/vị trí. "
            "Đổi địa điểm hoặc góc máy cắt cảnh thì continuation=false. Chia thành các cảnh lớn hợp lý để tránh nối vô hạn; "
            "không lặp nguyên action, không thêm văn bản ngoài JSON. Không tự bịa đường dẫn ảnh."
        )
        try:
            call = self._call_with_json_repair
            data = copy.deepcopy(self.existing) if self.existing else call(instruction)
            if not self.existing:
                data, fixes = normalize_location_cuts(data)
                data, linked = link_continuation_states(data)
                if linked:
                    self.progress.emit(f"Đã liên kết {linked} trạng thái nối cảnh từ kết thúc clip trước.")
                if fixes:
                    self.progress.emit(f"Đã chuẩn hóa {fixes} đánh dấu cảnh/nối cảnh theo bối cảnh.")
            self._validate_partial(data)
            self._checkpoint(data)
            last_error = ""
            for attempt in range(3):
                missing = self.num_scenes - len(data["shots"])
                if not missing:
                    break
                source_name = "Muse" if self.provider == "muse" else "AI"
                self.progress.emit(f"Đã có {len(data['shots'])}/{self.num_scenes} clip. {source_name} đang viết bổ sung {missing} clip…")
                continuation = (
                    f"CHỈ VIẾT PHẦN BỔ SUNG: đúng {missing} clip MỚI.\n"
                    + instruction.replace(f"gồm đúng {self.num_scenes} clip", f"tổng cộng {self.num_scenes} clip")
                    + f"\nĐÃ CÓ {len(data['shots'])} clip. Lần này chỉ trả đúng {missing} clip MỚI tiếp theo; "
                    "không viết lại hoặc trả lại các clip đã có. Giữ nguyên ID/mô tả nhân vật và địa điểm cũ. "
                    "characters/locations chỉ cần chứa định nghĩa mới, hoặc mảng rỗng. "
                    "Nếu tiếp nối clip cuối, sao chép nguyên văn end_state vào start_state và giữ sequence/location_id. "
                    "Nếu chuyển cảnh, continuation=false. Giữ mạch truyện; nếu câu chuyện đã khép lại, "
                    "viết đoạn kết nối tiếp hợp lý, không đảo ngược các sự kiện đã xảy ra. "
                    "Mọi action phải khác các action trước; không lặp hoặc thêm clip rỗng cho đủ số lượng. "
                    f"\nLỗi cấu trúc của phần bổ sung lần trước (nếu có): {last_error}"
                    "\nBẢN ĐÃ GIỮ, CHỈ ĐỂ THAM KHẢO, KHÔNG TRẢ LẠI: " + json.dumps(data, ensure_ascii=False)
                )
                # Transport/quota errors propagate; do not repeat a paid request
                # just because the API is unavailable. Only invalid structure is retried.
                extra = call(continuation)
                try:
                    candidate = self._append(data, extra)
                except ValueError as exc:
                    last_error = str(exc)
                    continue
                data = candidate
                last_error = ""
                self._checkpoint(data)
            if len(data["shots"]) != self.num_scenes:
                raise ValueError(f"Đã giữ {len(data['shots'])}/{self.num_scenes} clip, còn thiếu {self.num_scenes-len(data['shots'])}. "
                                 "Bấm Viết tiếp để tiếp tục từ bản nháp, không cần tạo lại phần đã có.")
            project = apply_storyboard(data, "Kiểm tra", self.seconds, self.clip_seconds, "16:9", "", self.notes)
            issues = inspect_project(project)
            if issues:
                self.progress.emit("Đang chỉnh các cảnh có mô tả nhạy cảm trước khi gửi Muse…")
                candidate = call(
                    instruction + "\nRÀ VÀ CHỈNH KỊCH BẢN DƯỚI ĐÂY MỘT LẦN: giữ nguyên số clip, thứ tự, "
                    "ID/tên nhân vật và địa điểm, cách nối cảnh. Chuyển cảnh rủi ro thành hành động "
                    "phù hợp thực sự; cập nhật cả start_state/end_state và các trạng thái nối tiếp, "
                    "không chỉ dùng từ đồng nghĩa để che nội dung cũ. Trả toàn bộ JSON.\n"
                    + describe_issues(issues) + "\n" + json.dumps(data, ensure_ascii=False))
                candidate, _ = link_continuation_states(candidate)
                repaired = apply_storyboard(candidate, "Kiểm tra", self.seconds, self.clip_seconds, "16:9", "", self.notes)
                for key in ("characters", "locations"):
                    if [(r["id"], r["name"]) for r in candidate[key]] != [(r["id"], r["name"]) for r in data[key]]:
                        raise ValueError("Bản chỉnh nội dung đã thay ID/tên tham chiếu. Bản nháp cũ vẫn được giữ.")
                if any((a.sequence, a.continuation, a.character_ids, a.location_id) !=
                       (b.sequence, b.continuation, b.character_ids, b.location_id)
                       for a, b in zip(project.shots, repaired.shots)):
                    raise ValueError("Bản chỉnh nội dung đã thay cách nối/gán tham chiếu. Bản nháp cũ vẫn được giữ.")
                remaining = inspect_project(repaired)
                if remaining:
                    raise ValueError(describe_issues(remaining))
                data = candidate
                self._checkpoint(data)
            self.storyboard_ready.emit(data)
        except Exception as exc:
            self.error_signal.emit("Chưa lập được storyboard: " + str(exc).replace(self.api_key, "[ẩn]"))
