"""Optional Gemini visual comparison; never claims deterministic identity matching."""
import base64
import json
from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QImage
import requests
from workers.llm_rewriter import LLMRewriterWorker
from core.film_project import shot_reference_assets
from core.film_skills import skill_instruction, skill_provenance
from utils.film_media import extract_frame_at
from pathlib import Path


def image_part(path):
    image = QImage(path)
    if image.isNull():
        raise ValueError("Không đọc được ảnh cần đối chiếu.")
    image = image.scaled(768, 768, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG", 85)
    return {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(bytes(buffer.data())).decode()}}


def review_shot(store, shot, config, stop=None):
    key = config.get("gemini_api_key", "")
    if not key:
        raise ValueError("Cần API key Gemini để đối chiếu hình ảnh.")
    files, audit = shot_reference_assets(store, shot)
    if not files:
        raise ValueError("Clip chưa được gán nhân vật/bối cảnh có ảnh chuẩn để đối chiếu.")
    parts = [{"text": skill_instruction('review') + "\nĐối chiếu ảnh CHUẨN được đánh nhãn với các KHUNG MẪU VIDEO. "
             "Chỉ kiểm tra nhận dạng, màu sắc/trang phục/đạo cụ đặc trưng và bố cục/vật mốc của địa điểm. "
             "Đừng coi đổi tư thế, góc máy, cỡ cảnh là sai nhân vật. Ảnh nhân vật không khóa nền. "
             "Nếu thấy lệch hoặc không đủ bằng chứng hãy dùng verdict=review; chỉ pass khi có đủ bằng chứng. "
             "Không phán đoán chuyển động giữa các ảnh, không khẳng định đã kiểm tra toàn bộ video. "
             f"Hành động dự kiến: {shot.prompt}. Đầu: {shot.start_state}. Cuối: {shot.end_state}. "
             'Trả JSON duy nhất: {"verdict":"pass hoặc review","summary":"nhận xét tiếng Việt",'
             '"issues":["vấn đề kèm nhãn ảnh bằng chứng"],'
             '"correction":"none hoặc reference hoặc shot_plan hoặc generation hoặc capability hoặc manual"}.'}]
    for path, item in zip(files, audit):
        parts.extend([{"text": f"CHUẨN {item['kind']}: {item['name']}"}, image_part(path)])
    shot_index = next(i for i, item in enumerate(store.project.shots) if item.id == shot.id)
    previous_evidence = None
    if shot.continuation and shot_index > 0:
        previous = store.project.shots[shot_index-1]
        if previous.last_frame:
            parts.extend([{'text':'BÀN GIAO: khung cuối clip trước'}, image_part(store.asset(previous.last_frame))])
            previous_evidence = {'path': previous.last_frame, 'sha256': store.digest(store.asset(previous.last_frame))}
    samples = [('KẾT QUẢ VIDEO: đầu clip', shot.first_frame)]
    clip = Path(store.asset(shot.clip))
    for fraction in (.25, .5, .75):
        if stop and stop():
            raise InterruptedError('Đã dừng đối chiếu clip.')
        sample = extract_frame_at(str(clip), clip.with_name(clip.stem + f'_qa{int(fraction*100):02d}.png'),
                                  shot.timeline_seconds * fraction, stop)
        samples.append((f'KẾT QUẢ VIDEO: {int(fraction*100)}% clip', store.relative(sample)))
    samples.append(('KẾT QUẢ VIDEO: cuối clip', shot.last_frame))
    for name, relative in samples:
        parts.extend([{"text": name}, image_part(store.asset(relative))])
    client = LLMRewriterWorker("", 0, [], "gemini", key, config.get("gemini_model", "auto"))
    model = client.model_name
    if not model or model == "auto":
        model = client._available_gemini_model()
    payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0}}
    def call(name):
        return requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent",
                             headers={"x-goog-api-key": key}, json=payload, timeout=90)
    response = call(model)
    if response.status_code == 404:
        model = client._available_gemini_model(exclude=model)
        response = call(model)
    if response.status_code != 200:
        raise ValueError(f"Gemini chưa đối chiếu được hình ảnh (HTTP {response.status_code}).")
    raw = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    data = json.loads(raw)
    if (data.get("verdict") not in ("pass", "review") or not isinstance(data.get("summary"), str)
            or not isinstance(data.get("issues"), list) or any(not isinstance(x, str) for x in data["issues"])):
        raise ValueError("Kết quả đối chiếu Gemini không hợp lệ.")
    correction = data.get('correction', 'manual' if data['verdict'] == 'review' else 'none')
    if correction not in ('none', 'reference', 'shot_plan', 'generation', 'capability', 'manual'):
        raise ValueError('Kết quả đối chiếu có đề xuất sửa không hợp lệ.')
    if data["issues"] and correction == 'none':
        correction = 'manual'
    if data["issues"] or correction != 'none':
        data["verdict"] = "review"
    return {**data, 'correction': correction, "model": model, "scope": "five_sampled_frames_only", "references": audit,
            'skills': skill_provenance(),
            'previous_frame': previous_evidence,
            'samples': [{'label': name, 'path': path, 'sha256': store.digest(store.asset(path))} for name,path in samples],
            "first_sha256": store.digest(store.asset(shot.first_frame)),
            "last_sha256": store.digest(store.asset(shot.last_frame))}
