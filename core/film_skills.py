"""Reviewed, stage-specific adapters for pinned third-party film skill documents.

Upstream documents are archival data. We never run upstream scripts, commands,
installers or arbitrary instructions, and never download skills at app startup.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys


def skill_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'assets' / 'film_skills'


@lru_cache(maxsize=1)
def _bundle():
    root = skill_root()
    runtime_bytes = (root/'runtime.json').read_bytes()
    sources_bytes = (root/'sources.json').read_bytes()
    runtime = json.loads(runtime_bytes)
    manifest = json.loads(sources_bytes)
    for source in manifest['sources']:
        for file in source['files']:
            path = (root/file['path']).resolve()
            if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != file['sha256']:
                raise ValueError('Bộ hướng dẫn sản xuất phim không toàn vẹn. Cài lại bản app chính thức.')
    for stage in ('storyboard', 'reference', 'video', 'review'):
        if not isinstance(runtime['stages'][stage]['instruction'], str) or not runtime['stages'][stage]['instruction'].strip():
            raise ValueError('Thiếu hướng dẫn cho bước sản xuất phim.')
    return runtime, manifest, hashlib.sha256(runtime_bytes + sources_bytes).hexdigest()


def skill_instruction(stage):
    runtime, _, _ = _bundle()
    return runtime['stages'][stage]['instruction']


def skill_provenance():
    runtime, manifest, digest = _bundle()
    return {'version': runtime['version'], 'sha256': digest,
            'sources': [{'repository': s['repository'], 'commit': s['commit'], 'license': s['license']}
                        for s in manifest['sources']]}
