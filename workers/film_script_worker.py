"""Generate a coherent film outline through the configured LLM, without filler fallback."""
from workers.llm_rewriter import LLMRewriterWorker


class FilmScriptWorker(LLMRewriterWorker):
    def __init__(self, idea, seconds, scene_count, notes, provider, api_key, model_name):
        super().__init__(idea, scene_count, [], provider, api_key, model_name)
        self.seconds = seconds
        self.notes = notes

    def run(self):
        if not self.api_key or self.provider not in ("gemini", "openai", "anthropic"):
            self.error_signal.emit("Chọn Gemini, OpenAI hoặc Anthropic và nhập API key trong Cài đặt AI để tạo kịch bản từ ý tưởng.")
            return
        instruction = (
            f"Bạn là biên kịch. Từ ý tưởng của người dùng, viết đúng {self.num_scenes} cảnh lớn "
            f"cho phim dài {self.seconds} giây. Câu chuyện có mở đầu, phát triển và kết thúc rõ ràng. "
            "Giữ nhất quán nhân vật, bối cảnh và trình tự thời gian; mỗi cảnh mô tả cụ thể chủ thể, "
            "hành động, địa điểm, ánh sáng và hướng máy, đủ để phát triển thành các clip tiếp nối. "
            "Không lặp cảnh cho đủ số lượng, không thêm nhân vật chung chung ngoài ý tưởng. "
            f"Quy tắc nhân vật/phong cách của người dùng: {self.notes or 'Suy ra nhất quán từ ý tưởng.'} "
            "Viết tiếng Việt. Chỉ trả về một JSON array các chuỗi, mỗi chuỗi là một cảnh lớn, "
            "không đánh số, không markdown, không giải thích."
        )
        try:
            prompts = {"gemini": self._call_gemini, "openai": self._call_openai,
                       "anthropic": self._call_anthropic}[self.provider](instruction)
            if (not isinstance(prompts, list) or len(prompts) != self.num_scenes
                    or any(not isinstance(p, str) or not p.strip() for p in prompts)):
                raise ValueError("AI chưa trả đủ các cảnh. Hãy thử tạo lại.")
            self.finished_signal.emit([p.strip() for p in prompts])
        except Exception as exc:
            message = str(exc).replace(self.api_key, "[ẩn]")
            self.error_signal.emit(f"Chưa tạo được kịch bản: {message}")
