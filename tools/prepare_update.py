"""Prepare GitHub Release metadata; never publishes or uploads files."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.version import APP_VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/repository (public)")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("Repo must be owner/repository")
    root = Path(__file__).resolve().parent.parent
    installer = root / "dist" / f"AutoMuseAI_Setup_v{APP_VERSION}.exe"
    digest = hashlib.sha256()
    with installer.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    metadata = {"version": APP_VERSION, "size": installer.stat().st_size,
                "sha256": digest.hexdigest(),
                "installer_url": f"https://github.com/{args.repo}/releases/download/v{APP_VERSION}/{installer.name}"}
    target = root / "dist" / "update" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Upload {installer.name} and latest.json to release v{APP_VERSION}.")
    print(f"App source: https://github.com/{args.repo}/releases/latest/download/latest.json")


if __name__ == "__main__":
    main()
