from PyQt6.QtCore import QThread
from workers.llm_rewriter import LLMRewriterWorker


class GeminiKeyWorker(QThread):
    """One tiny generateContent call verifies inference, not only models.list."""
    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.key, self.error, self.model = key, '', ''

    def run(self):
        try:
            client = LLMRewriterWorker('Kiểm tra kết nối.', 1, [], 'gemini', self.key, 'auto')
            client.request_timeout = 30
            client.max_output_tokens = 256
            client.structured_schema = {'type':'ARRAY', 'items':{'type':'STRING'}}
            result = client._call_gemini('Chỉ trả một mảng JSON gồm một chuỗi ngắn: ["OK"].')
            if not result:
                raise ValueError('Gemini chưa trả lời phép thử tạo văn bản.')
            self.model = client.model_name
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, ValueError) else 'Chưa kiểm tra được Gemini. Thử lại sau.'
            self.error = self.error.replace(self.key, '[ẩn]') if self.key else self.error
