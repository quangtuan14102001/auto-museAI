import copy
import json
import unittest
from unittest.mock import Mock, patch
from core.storyboard_json import decode_storyboard_json, InvalidStoryboardJSON
from workers.film_storyboard_worker import FilmStoryboardWorker
from test_storyboard_completion import data


class StoryboardJSONTests(unittest.TestCase):
    def worker(self, seconds=600):
        return FilmStoryboardWorker("Mèo và chuột", seconds, 10, "", "gemini", "test-key", "model", genre="Kinh dị")

    def test_trailing_comma_fix_does_not_change_quoted_dialogue(self):
        original = data(2)
        original["shots"][0]["action"] = 'Mèo nhìn ký hiệu ,} và nói "Ai đó?"'
        raw = json.dumps(original, ensure_ascii=False)
        broken = raw[:-2] + ",]}"
        self.assertEqual(decode_storyboard_json(broken), original)

    def test_unquoted_key_after_48_complete_shots_preserves_prefix(self):
        original = data(48)
        broken = json.dumps(original)[:-2] + ', {action: "broken"}]}'
        self.assertEqual(decode_storyboard_json(broken), original)

    def test_truncated_final_shot_is_not_fabricated(self):
        original = data(48)
        raw = json.dumps(original)
        broken = raw[:raw.rfind('{"action"')] + '{"action":"unfinished'
        recovered = decode_storyboard_json(broken)
        self.assertEqual(recovered["shots"], original["shots"][:47])

    def test_no_prefix_without_canonical_definitions(self):
        with self.assertRaises(InvalidStoryboardJSON):
            decode_storyboard_json('{"characters": [{bad: "value"}')

    def test_parser_recovery_flows_into_missing_shot_completion(self):
        worker = self.worker()
        original = data(48)
        broken = json.dumps(original)[:-2] + ', {action: "broken"}]}'
        outputs, errors = [], []
        worker.storyboard_ready.connect(outputs.append)
        worker.error_signal.connect(errors.append)
        with patch.object(worker, "_call_gemini", side_effect=lambda instruction:
                          worker._extract_json_array(broken) if "CHỈ VIẾT PHẦN BỔ SUNG" not in instruction
                          else data(12, 48)) as api:
            worker.run()
        self.assertFalse(errors)
        self.assertEqual(api.call_count, 2)
        self.assertEqual(len(outputs[0]["shots"]), 60)
        self.assertEqual(outputs[0]["shots"][:48], original["shots"])

    def test_unrecoverable_json_is_repaired_once_only(self):
        worker = self.worker(20)
        outputs = []
        worker.storyboard_ready.connect(outputs.append)
        with patch.object(worker, "_call_gemini", side_effect=[InvalidStoryboardJSON(), data(2)]) as api:
            worker.run()
        self.assertEqual(api.call_count, 2)
        self.assertEqual(len(outputs), 1)
        self.assertIn("CHỈ SỬA CÚ PHÁP JSON", api.call_args.args[0])

    def test_repair_failure_has_friendly_error_and_no_infinite_retry(self):
        worker = self.worker(20)
        errors = []
        worker.error_signal.connect(errors.append)
        with patch.object(worker, "_call_gemini", side_effect=InvalidStoryboardJSON()) as api:
            worker.run()
        self.assertEqual(api.call_count, 2)
        self.assertIn("chưa đúng định dạng", errors[0])
        self.assertNotIn("Expecting property", errors[0])

    def test_gemini_receives_json_mode_and_schema(self):
        worker = self.worker(20)
        response = Mock(status_code=200)
        response.json.return_value = {"candidates": [{"content": {"parts": [{"text": json.dumps(data(2))}]}}]}
        with patch("workers.llm_rewriter.requests.post", return_value=response) as api:
            worker._call_gemini("instruction")
        config = api.call_args.kwargs["json"]["generationConfig"]
        self.assertEqual(config["responseMimeType"], "application/json")
        self.assertIn("shots", config["responseSchema"]["required"])
