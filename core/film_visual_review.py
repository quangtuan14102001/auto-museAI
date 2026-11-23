"""Optional Gemini visual comparison; never claims deterministic identity matching."""
import base64
import json
from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QImage
import requests
from workers.llm_rewriter import LLMRewriterWorker
from core.film_project import shot_reference_assets


def image_part(path):
    image = QImage(path)
    if image.isNull():
        raise ValueError("Không đọc được ảnh cần đối chiếu.")
    image = image.scaled(768, 768, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG", 85)
    return {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(bytes(buffer.data())).decode()}}


def review_shot(store, shot, config):
    key = config.get("gemini_api_key", "")
    if not key:
        raise ValueError("Cần API key Gemini để đối chiếu hình ảnh.")
    files, audit = shot_reference_assets(store, shot)
    if not files:
        raise ValueError("Clip chưa được gán nhân vật/bối cảnh có ảnh chuẩn để đối chiếu.")
    parts = [{"text": "Đối chiếu ảnh CHUẨN được đánh nhãn với hai ảnh KẾT QUẢ VIDEO. "
             "Chỉ kiểm tra nhận dạng, màu sắc/trang phục/đạo cụ đặc trưng và bố cục/vật mốc của địa điểm. "
             "Đừng coi đổi tư thế, góc máy, cỡ cảnh là sai nhân vật. Ảnh nhân vật không khóa nền. "
             "Nếu thấy lệch hoặc không đủ bằng chứng hãy dùng verdict=review; chỉ pass khi có đủ bằng chứng. "
             "Không phán đoán chuyển động giữa hai ảnh, không khẳng định đã kiểm tra toàn bộ video. "
             f"Hành động dự kiến: {shot.prompt}. Đầu: {shot.start_state}. Cuối: {shot.end_state}. "
             'Trả JSON duy nhất: {"verdict":"pass hoặc review","summary":"nhận xét tiếng Việt","issues":["vấn đề"]}.'}]
    for path, item in zip(files, audit):
        parts.extend([{"text": f"CHUẨN {item['kind']}: {item['name']}"}, image_part(path)])
    for name, relative in [("KẾT QUẢ VIDEO: đầu clip", shot.first_frame), ("KẾT QUẢ VIDEO: cuối clip", shot.last_frame)]:
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
    if data["issues"]:
        data["verdict"] = "review"
    return {**data, "model": model, "scope": "first_and_last_frames_only", "references": audit,
            "first_sha256": store.digest(store.asset(shot.first_frame)),
            "last_sha256": store.digest(store.asset(shot.last_frame))}
