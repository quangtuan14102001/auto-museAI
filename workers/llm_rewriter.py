import json
import requests
from typing import List, Dict
from PyQt6.QtCore import QThread, pyqtSignal
from utils.logger import log_event


class LLMRewriterWorker(QThread):
    finished_signal = pyqtSignal(list) # List of generated prompt strings
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        raw_script: str,
        num_scenes: int,
        alias_tags: List[str],
        provider: str = "gemini",
        api_key: str = "",
        model_name: str = ""
    ):
        super().__init__()
        self.raw_script = raw_script
        self.num_scenes = num_scenes
        self.alias_tags = alias_tags
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name

    def run(self):
        if not self.raw_script.strip():
            self.error_signal.emit("Kịch bản thô không được để trống!")
            return

        log_event(f"Bắt đầu phân tích & viết lại kịch bản với LLM ({self.provider})...")

        system_instruction = (
            "Bạn là chuyên gia biên kịch và tạo video AI điện ảnh. "
            f"Nhiệm vụ: Chuyển kịch bản thô sau đây thành đúng {self.num_scenes} phân cảnh prompt chi tiết (dùng cho AI video generator). "
            f"Nếu phù hợp, hãy khéo léo chèn các thẻ tham chiếu nhân vật/sản phẩm sau vào các phân cảnh: {', '.join(self.alias_tags)}. "
            "Trả về kết quả dưới dạng danh sách JSON các chuỗi prompt, ví dụ: [\"Prompt cảnh 1...\", \"Prompt cảnh 2...\"]. "
            "Chỉ trả về JSON hợp lệ, không giải thích thêm."
        )

        try:
            if not self.api_key:
                # Built-in smart local heuristic scene generator
                prompts = self._local_scene_generator()
            elif self.provider == "gemini":
                prompts = self._call_gemini(system_instruction)
            elif self.provider == "openai":
                prompts = self._call_openai(system_instruction)
            elif self.provider == "anthropic":
                prompts = self._call_anthropic(system_instruction)
            else:
                prompts = self._local_scene_generator()

            if (not isinstance(prompts, list) or len(prompts) != self.num_scenes
                    or any(not isinstance(prompt, str) or not prompt.strip() for prompt in prompts)):
                raise ValueError("LLM không trả đúng số lượng phân cảnh văn bản hợp lệ.")
            log_event(f"Đã tạo thành công {len(prompts)} phân cảnh prompt từ kịch bản.", "SUCCESS")
            self.finished_signal.emit(prompts)
        except Exception as e:
            log_event(f"Lỗi khi viết lại kịch bản với LLM: {e}", "WARNING")
            log_event("Chuyển sang bộ phân tách kịch bản thông minh cục bộ...")
            prompts = self._local_scene_generator()
            self.finished_signal.emit(prompts)

    def _local_scene_generator(self) -> List[str]:
        """Intelligent local fallback generator."""
        lines = [line.strip() for line in self.raw_script.splitlines() if line.strip()]
        if not lines:
            lines = [self.raw_script.strip()]

        prompts = []
        tags_str = " ".join(self.alias_tags[:2]) if self.alias_tags else ""

        for idx, line in enumerate(lines[:self.num_scenes], 1):
            tag_insertion = f" có {tags_str}" if tags_str and idx % 2 == 1 else ""
            p = f"Phân cảnh #{idx}: {line}{tag_insertion}, phong cách điện ảnh ánh sáng rực rỡ, góc máy chuyển động mượt mà 4K cinematic"
            prompts.append(p)

        # If user asked for more scenes than available lines
        while len(prompts) < self.num_scenes:
            idx = len(prompts) + 1
            prompts.append(f"Phân cảnh #{idx}: Cận cảnh cảm xúc nhân vật {tags_str}, biểu cảm chân thực, góc quay nghệ thuật 8K")

        return prompts

    def _call_gemini(self, instruction: str) -> List[str]:
        model = (self.model_name or "auto").removeprefix("models/")
        if model == "auto":
            model = self._available_gemini_model()
        prompt_content = f"{instruction}\n\nKỊCH BẢN GỐC:\n{self.raw_script}"
        payload = {
            "contents": [{"parts": [{"text": prompt_content}]}],
            "generationConfig": {"temperature": 0.7}
        }
        if getattr(self, "structured_schema", None):
            payload["generationConfig"].update(responseMimeType="application/json", responseSchema=self.structured_schema)
        headers = {"x-goog-api-key": self.api_key}
        def generate(name):
            return requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent",
                                 json=payload, headers=headers, timeout=getattr(self, "request_timeout", 60))
        resp = generate(model)
        if resp.status_code == 404:
            # A rejected model request created no content: discover accessible
            # text models and retry once, without retrying quota/network errors.
            model = self._available_gemini_model(exclude=model)
            resp = generate(model)
        if resp.status_code != 200:
            messages = {401: "API key Gemini không hợp lệ.", 403: "API key chưa được phép dùng Gemini.",
                        429: "Gemini đã hết hạn mức hoặc đang giới hạn lượt gọi. Kiểm tra quota trong Google AI Studio.",
                        404: "Gemini chưa cung cấp model tạo văn bản khả dụng cho API key này."}
            raise ValueError(messages.get(resp.status_code, f"Gemini chưa xử lý được yêu cầu (HTTP {resp.status_code}). Hãy thử lại sau."))
        self.model_name = model
        data = resp.json()
        raw_reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return self._extract_json_array(raw_reply)

    def _available_gemini_model(self, exclude=""):
        models, token = [], ""
        for _ in range(10):
            params = {"pageSize": 100}
            if token:
                params["pageToken"] = token
            response = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                                    headers={"x-goog-api-key": self.api_key}, params=params, timeout=30)
            if response.status_code != 200:
                raise ValueError(f"Không đọc được danh sách model Gemini (HTTP {response.status_code}). Kiểm tra API key/quyền truy cập.")
            data = response.json()
            for item in data.get("models", []):
                name = item.get("name", "").removeprefix("models/")
                if (name != exclude and name.startswith("gemini-")
                        and "generateContent" in item.get("supportedGenerationMethods", [])
                        and not any(word in name for word in ("image", "tts", "audio", "live", "robotics", "computer-use"))):
                    models.append(name)
            token = data.get("nextPageToken", "")
            if not token:
                break
        if not models:
            raise ValueError("API key này chưa có model Gemini tạo văn bản khả dụng.")
        # Favor stable Flash text models. The actual names come from Google's
        # response rather than hardcoded model versions that can be retired.
        return sorted(models, key=lambda n: (n != "gemini-flash-lite-latest", "preview" in n or "exp" in n,
                      "flash" not in n, "lite" in n, n), reverse=False)[0]

    def _call_openai(self, instruction: str) -> List[str]:
        model = self.model_name or "gpt-4o"
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": f"KỊCH BẢN GỐC:\n{self.raw_script}"}
            ],
            "temperature": 0.7
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=45)
        if resp.status_code != 200:
            raise Exception(f"OpenAI API Error: {resp.status_code} - {resp.text}")
        data = resp.json()
        raw_reply = data["choices"][0]["message"]["content"].strip()
        return self._extract_json_array(raw_reply)

    def _call_anthropic(self, instruction: str) -> List[str]:
        model = self.model_name or "claude-3-5-sonnet-20241022"
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": model,
            "max_tokens": getattr(self, "max_output_tokens", 1500),
            "system": instruction,
            "messages": [{"role": "user", "content": f"KỊCH BẢN GỐC:\n{self.raw_script}"}]
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=45)
        if resp.status_code != 200:
            raise Exception(f"Claude API Error: {resp.status_code} - {resp.text}")
        data = resp.json()
        raw_reply = data["content"][0]["text"].strip()
        return self._extract_json_array(raw_reply)

    def _extract_json_array(self, text: str) -> List[str]:
        # Remove code fences
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        parsed = json.loads(clean)
        if not isinstance(parsed, list) or not parsed or any(not isinstance(x, str) or not x.strip() for x in parsed):
            raise ValueError("Kết quả LLM phải là danh sách các prompt văn bản không rỗng.")
        return [x.strip() for x in parsed]
