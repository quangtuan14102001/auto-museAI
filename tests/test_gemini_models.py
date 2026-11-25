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

    def test_invalid_key_400_is_recognized_without_leaking_body(self):
        response=Mock(status_code=400)
        response.json.return_value={'error':{'message':'test-key','details':[{'reason':'API_KEY_INVALID'}]}}
        with patch('workers.llm_rewriter.requests.post',return_value=response):
            with self.assertRaisesRegex(ValueError,'không hợp lệ') as error:
                self.worker('chosen-model')._call_gemini('instruction')
        self.assertNotIn('test-key',str(error.exception))

    def test_text_parts_are_joined_and_thoughts_are_not_json_output(self):
        response=Mock(status_code=200)
        response.json.return_value={'candidates':[{'content':{'parts':[
            {'text':'internal reasoning','thought':True}, {'text':'["sce'}, {'text':'ne"]'}]}}]}
        with patch('workers.llm_rewriter.requests.post',return_value=response):
            self.assertEqual(self.worker('chosen-model')._call_gemini('instruction'),['scene'])

    def test_blocked_output_is_not_misreported_as_key_failure(self):
        response=Mock(status_code=200)
        response.json.return_value={'promptFeedback':{'blockReason':'SAFETY'}}
        with patch('workers.llm_rewriter.requests.post',return_value=response):
            with self.assertRaisesRegex(ValueError,'chưa trả nội dung'):
                self.worker('chosen-model')._call_gemini('instruction')

    def test_connection_error_does_not_leak_provider_url(self):
        import requests
        with patch('workers.llm_rewriter.requests.post',side_effect=requests.ConnectionError('https://example.com/test-key')):
            with self.assertRaisesRegex(ValueError,'Chưa kết nối') as error:
                self.worker('chosen-model')._call_gemini('instruction')
        self.assertNotIn('test-key',str(error.exception))
