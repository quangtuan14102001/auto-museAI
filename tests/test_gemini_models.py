import unittest
from unittest.mock import Mock, patch
from workers.llm_rewriter import LLMRewriterWorker


class GeminiModelTests(unittest.TestCase):
    def worker(self, model="auto"):
        return LLMRewriterWorker("robot", 1, [], "gemini", "test-key", model)

    def listing(self):
        response = Mock(status_code=200)
        response.json.return_value = {"models": [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-flash-lite-latest", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-image", "supportedGenerationMethods": ["generateContent"]}]}
        return response

    def test_auto_prefers_discovered_text_alias(self):
        with patch("workers.llm_rewriter.requests.get", return_value=self.listing()):
            self.assertEqual(self.worker()._available_gemini_model(), "gemini-flash-lite-latest")

    def test_retired_model_retries_once_with_discovered_model(self):
        ok = Mock(status_code=200)
        ok.json.return_value = {"candidates": [{"content": {"parts": [{"text": '["scene"]'}]}}]}
        with patch("workers.llm_rewriter.requests.get", return_value=self.listing()), patch(
                "workers.llm_rewriter.requests.post", side_effect=[Mock(status_code=404), ok]) as post:
            self.assertEqual(self.worker("gemini-1.5-flash")._call_gemini("instruction"), ["scene"])
            self.assertEqual(post.call_count, 2)
            self.assertIn("gemini-flash-lite-latest", post.call_args.args[0])
            self.assertNotIn("test-key", post.call_args.args[0])

    def test_quota_error_does_not_retry(self):
        with patch("workers.llm_rewriter.requests.post", return_value=Mock(status_code=429)) as post, patch(
                "workers.llm_rewriter.requests.get") as get:
            with self.assertRaisesRegex(ValueError, "hạn mức"):
                self.worker("chosen-model")._call_gemini("instruction")
            self.assertEqual(post.call_count, 1)
            get.assert_not_called()
