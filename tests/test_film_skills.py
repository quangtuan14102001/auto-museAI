import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtGui import QImage
from core.film_skills import _bundle, skill_instruction, skill_provenance, skill_root
from core.film_project import FilmReference, film_prompt, FilmStore
from core.film_visual_review import review_shot
from workers.film_worker import prepare_shot
from test_film_projects import Fixture


class SkillBundleTests(unittest.TestCase):
    def test_stage_adapters_and_pinned_sources_are_available_offline(self):
        with patch('requests.get', side_effect=AssertionError('No skill download at runtime')):
            self.assertIn('QUY TRÌNH BIÊN KỊCH', skill_instruction('storyboard'))
            self.assertIn('HỒ SƠ ẢNH CHUẨN', skill_instruction('reference'))
            self.assertIn('ĐẠO DIỄN CLIP', skill_instruction('video'))
            self.assertIn('BẰNG CHỨNG', skill_instruction('review'))
            provenance = skill_provenance()
            self.assertEqual(len(provenance['sources']), 4)
            self.assertEqual(len(provenance['sha256']), 64)
        manifest = json.loads((skill_root()/'sources.json').read_text(encoding='utf-8'))
        self.assertEqual(sum(f['path'].endswith('SKILL.md') for s in manifest['sources'] for f in s['files']), 8)

    def test_changed_document_is_rejected_instead_of_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'skills'
            shutil.copytree(skill_root(), target)
            document = next(target.rglob('SKILL.md'))
            document.write_text('tampered content', encoding='utf-8')
            _bundle.cache_clear()
            try:
                with patch('core.film_skills.skill_root', return_value=target):
                    with self.assertRaisesRegex(ValueError, 'không toàn vẹn'):
                        skill_instruction('storyboard')
            finally:
                _bundle.cache_clear()


class SkillReviewTests(unittest.TestCase, Fixture):
    @classmethod
    def setUpClass(cls):
        cls.make_media()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setup_shot(self, name):
        store = self.store(name, 5, review=False)
        store.project.visual_review_enabled = True
        prepare_shot(store, 0, self.source)
        shot = store.project.shots[0]
        ref = FilmReference('robot', 'character', 'Rô', 'Màu sắc cố định',
                            images=[store.snapshot(store.asset(shot.first_frame), 'canonical')])
        store.project.references = [ref]
        shot.character_ids = ['robot']
        store.save()
        return store, shot

    def test_five_sample_review_has_evidence_and_cannot_auto_pass_with_findings(self):
        store, shot = self.setup_shot('qa-samples')
        response = MagicMock(status_code=200)
        response.json.return_value = {'candidates':[{'content':{'parts':[{'text':json.dumps({
            'verdict':'pass', 'summary':'Màu khác ở 75%', 'issues':['75%: đổi màu'], 'correction':'reference'})}]}}]}
        with patch('core.film_visual_review.requests.post', return_value=response) as api:
            result = review_shot(store, shot, {'gemini_api_key':'fixture-key', 'gemini_model':'fixture-model'})
        self.assertEqual(api.call_count, 1)
        self.assertEqual(result['scope'], 'five_sampled_frames_only')
        self.assertEqual(result['verdict'], 'review')
        self.assertEqual(result['correction'], 'reference')
        self.assertEqual(len(result['samples']), 5)
        self.assertTrue(all(store.digest(store.asset(s['path'])) == s['sha256'] for s in result['samples']))
        parts = api.call_args.kwargs['json']['contents'][0]['parts']
        self.assertEqual(sum('inlineData' in p for p in parts), 6)  # one canonical + five samples
        self.assertIn('không tuyên bố đã xem toàn video', parts[0]['text'])
        # The midpoint is decoded from the source; it is not a duplicate path to the first frame.
        first = QImage(store.asset(result['samples'][0]['path']))
        middle = QImage(store.asset(result['samples'][3]['path']))
        self.assertNotEqual(first.pixelColor(10,10), middle.pixelColor(10,10))

    def test_pending_visual_review_cannot_be_exported_after_restart(self):
        store, shot = self.setup_shot('qa-checkpoint')
        self.assertEqual(shot.status, 'REVIEW')
        self.assertFalse(store.project.ready_to_export)
        reopened = FilmStore.load(store.manifest)
        self.assertFalse(reopened.project.ready_to_export)
        self.assertEqual(reopened.project.shots[0].approved_by, '')

    def test_continuation_review_includes_previous_clip_handoff(self):
        store = self.store('qa-handoff', 6, review=False)
        prepare_shot(store, 0, self.source)
        prepare_shot(store, 1, self.source)
        shot = store.project.shots[1]
        store.project.references = [FilmReference('subject', 'character', 'Subject', 'Same subject',
                                    images=[store.snapshot(store.asset(shot.first_frame), 'canonical')])]
        shot.character_ids = ['subject']
        response = MagicMock(status_code=200)
        response.json.return_value = {'candidates':[{'content':{'parts':[{'text':json.dumps({
            'verdict':'pass','summary':'Đủ bằng chứng ở khung mẫu','issues':[],'correction':'none'})}]}}]}
        with patch('core.film_visual_review.requests.post', return_value=response) as api:
            result = review_shot(store, shot, {'gemini_api_key':'fixture-key','gemini_model':'fixture-model'})
        parts = api.call_args.kwargs['json']['contents'][0]['parts']
        self.assertTrue(any(p.get('text') == 'BÀN GIAO: khung cuối clip trước' for p in parts))
        self.assertEqual(sum('inlineData' in p for p in parts), 7)
        self.assertEqual(result['previous_frame']['path'], store.project.shots[0].last_frame)
        self.assertEqual(result['previous_frame']['sha256'], store.digest(store.asset(store.project.shots[0].last_frame)))

    def test_video_prompt_uses_frozen_identity_and_current_shot_guide(self):
        store, shot = self.setup_shot('qa-prompt')
        prompt = film_prompt(store.project, shot)
        self.assertIn('[robot] Rô: Màu sắc cố định', prompt)
        self.assertIn('ĐẠO DIỄN CLIP HIỆN TẠI', prompt)
        self.assertIn(shot.prompt, prompt)
        self.assertNotIn('QUY TRÌNH BIÊN KỊCH', prompt)
