import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from workers.film_storyboard_worker import FilmStoryboardWorker, normalize_location_cuts, link_continuation_states, apply_storyboard


def data(count, start=0):
    return {"characters": [{"id": "robot", "name": "Rô", "description": "Robot trắng, ba lô đỏ"}],
            "locations": [{"id": "forest", "name": "Rừng", "description": "Rừng bình minh"}],
            "shots": [{"action": f"Hành động riêng {i}", "sequence": 1, "continuation": i > 0,
                       "character_ids": ["robot"], "location_id": "forest",
                       "start_state": f"Vị trí {i}", "end_state": f"Vị trí {i+1}"}
                      for i in range(start, start+count)]}


class StoryboardCompletionTests(unittest.TestCase):
    def test_location_change_becomes_cut_and_following_chain_stays_valid(self):
        original = data(5)
        original["locations"].append({"id": "cave", "name": "Hang", "description": "Hang đá"})
        for row in original["shots"][3:]:
            row["location_id"] = "cave"
        before = copy.deepcopy(original)
        fixed, count = normalize_location_cuts(original)
        project = apply_storyboard(fixed, "Film", 50, 10, "16:9", "", "")
        self.assertFalse(project.shots[3].continuation)
        self.assertTrue(project.shots[4].continuation)
        self.assertEqual(project.shots[3].sequence, project.shots[4].sequence)
        self.assertEqual(original, before)
        self.assertGreater(count, 0)
        self.assertEqual([r['action'] for r in fixed['shots']], [r['action'] for r in original['shots']])

    def test_supplement_location_cut_preserves_checkpoint_prefix(self):
        original = data(5)
        original["locations"].append({"id": "cave", "name": "Hang", "description": "Hang đá"})
        original['shots'][3]['location_id'] = original['shots'][4]['location_id'] = 'cave'
        fixed, _ = normalize_location_cuts(original, start=3)
        self.assertEqual(fixed['shots'][:3], original['shots'][:3])
        self.assertFalse(fixed['shots'][3]['continuation'])
        apply_storyboard(fixed, 'Film', 50, 10, '16:9', '', '')

    def test_sequence_metadata_fixed_but_state_mismatch_not_hidden(self):
        original = data(2)
        original['shots'][1]['sequence'] = 2
        fixed, _ = normalize_location_cuts(original)
        self.assertEqual(fixed['shots'][1]['sequence'], 1)
        fixed['shots'][1]['start_state'] = 'Completely different state'
        with self.assertRaisesRegex(ValueError, 'trạng thái đầu'):
            apply_storyboard(fixed, 'Film', 20, 10, '16:9', '', '')

    def test_initial_ai_location_mistake_no_longer_aborts_storyboard(self):
        original = data(60)
        original['locations'].append({'id':'cave','name':'Hang','description':'Hang đá'})
        for row in original['shots'][3:]:
            row['location_id'] = 'cave'
        worker = self.worker()
        with patch.object(worker, '_call_gemini', return_value=original) as call:
            worker.run()
        self.assertFalse(self.errors)
        self.assertEqual(call.call_count, 1)
        self.assertFalse(self.ready[0]['shots'][3]['continuation'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "draft.json"

    def tearDown(self):
        self.temp.cleanup()

    def worker(self, existing=None):
        worker = FilmStoryboardWorker("Robot tìm kho báu", 600, 10, "", "gemini", "test-key", "test-model",
                                      existing=existing, checkpoint_path=self.path)
        self.ready, self.partial, self.errors = [], [], []
        worker.storyboard_ready.connect(self.ready.append)
        worker.partial_ready.connect(self.partial.append)
        worker.error_signal.connect(self.errors.append)
        return worker

    def test_48_shots_are_preserved_and_12_are_appended(self):
        first, extra = data(48), data(12, 48)
        extra["characters"][0]["description"] = "Must not overwrite canonical identity"
        before = copy.deepcopy(first)
        worker = self.worker()
        with patch.object(worker, "_call_gemini", side_effect=[first, extra]) as call:
            worker.run()
        self.assertFalse(self.errors)
        self.assertEqual(len(self.ready[0]["shots"]), 60)
        self.assertEqual(self.ready[0]["shots"][:48], before["shots"])
        self.assertEqual(self.ready[0]["characters"], before["characters"])
        self.assertEqual(first, before)
        self.assertEqual(call.call_count, 2)
        self.assertIn("đúng 12 clip MỚI", call.call_args.args[0])
        self.assertNotIn("gồm đúng 60 clip", call.call_args.args[0])
        self.assertEqual(len(json.loads(self.path.read_text(encoding="utf-8"))["shots"]), 60)

    def test_service_failure_keeps_partial_and_does_not_retry_quota(self):
        worker = self.worker()
        with patch.object(worker, "_call_gemini", side_effect=[data(48), ValueError("quota")]) as call:
            worker.run()
        self.assertEqual(call.call_count, 2)
        self.assertFalse(self.ready)
        self.assertEqual(len(self.partial[0]["shots"]), 48)
        self.assertEqual(len(json.loads(self.path.read_text(encoding="utf-8"))["shots"]), 48)
        self.assertTrue(self.errors)

    def test_resume_calls_only_for_missing_shots(self):
        worker = self.worker(existing=data(48))
        with patch.object(worker, "_call_gemini", return_value=data(12, 48)) as call:
            worker.run()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(len(self.ready[0]["shots"]), 60)

    def test_supplement_incoming_state_uses_checkpoint_without_mutating_prefix(self):
        extra = data(12, 48)
        extra["shots"][0]["start_state"] = "Wrong incoming state"
        worker = self.worker(existing=data(48))
        with patch.object(worker, "_call_gemini", side_effect=[extra, data(12, 48)]) as call:
            worker.run()
        self.assertEqual(call.call_count, 1)
        self.assertFalse(self.errors)
        self.assertEqual(self.ready[0]["shots"][48]["start_state"], "Vị trí 48")

    def test_state_link_keeps_actions_outgoing_states_and_cuts(self):
        original = data(4)
        original['shots'][1]['start_state'] = 'A paraphrase of position 1'
        original['shots'][2]['continuation'] = False
        original['shots'][2]['start_state'] = 'A deliberately different opening'
        original['shots'][3]['start_state'] = 'Wrong independently generated state'
        before = copy.deepcopy(original)
        linked, count = link_continuation_states(original)
        self.assertEqual(count, 2)
        self.assertEqual(linked['shots'][1]['start_state'], original['shots'][0]['end_state'])
        self.assertEqual(linked['shots'][2]['start_state'], original['shots'][2]['start_state'])
        for old, new in zip(original['shots'], linked['shots']):
            self.assertEqual(old['action'], new['action'])
            self.assertEqual(old['end_state'], new['end_state'])
        self.assertEqual(original, before)
        apply_storyboard(linked, 'Film', 40, 10, '16:9', '', '')

    def test_initial_18_clip_storyboard_with_state_mismatches_is_ready(self):
        original = data(18)
        for row in original['shots'][1:]:
            row['start_state'] = 'Independently worded incoming state'
        worker = FilmStoryboardWorker('mèo và chuột', 180, 10, '', 'gemini', 'test-key', 'model')
        ready, errors = [], []
        worker.storyboard_ready.connect(ready.append)
        worker.error_signal.connect(errors.append)
        with patch.object(worker, '_call_gemini', return_value=original) as call:
            worker.run()
        self.assertFalse(errors)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(len(ready[0]['shots']), 18)
        apply_storyboard(ready[0], 'Film', 180, 10, '16:9', '', '')

    def test_link_does_not_invent_missing_state_or_rewrite_kept_prefix(self):
        original = data(4)
        original['shots'][1]['start_state'] = 'Kept prefix'
        original['shots'][2]['start_state'] = ''
        linked, _ = link_continuation_states(original, start=2)
        self.assertEqual(linked['shots'][:2], original['shots'][:2])
        self.assertEqual(linked['shots'][2]['start_state'], '')

    def test_repeated_or_empty_supplements_stop_after_three_attempts(self):
        worker = self.worker(existing=data(48))
        with patch.object(worker, "_call_gemini", return_value=data(12, 0)) as call:
            worker.run()
        self.assertEqual(call.call_count, 3)
        self.assertFalse(self.ready)
        self.assertEqual(len(json.loads(self.path.read_text(encoding="utf-8"))["shots"]), 48)
        self.assertIn("Đã giữ 48/60", self.errors[0])
