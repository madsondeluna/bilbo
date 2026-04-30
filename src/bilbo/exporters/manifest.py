"""Write build manifest JSON."""

import json
from pathlib import Path


def write_manifest(build_dir: Path, generated_files: list[str]) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "build_dir": str(build_dir),
        "generated_files": generated_files,
    }
    out = build_dir / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out
