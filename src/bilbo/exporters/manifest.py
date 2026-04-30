"""Write build manifest JSON."""

import json
from pathlib import Path


def write_manifest(
    build_dir: Path,
    generated_files: list[str],
    bilbo_version: str = "",
    template_hashes: dict[str, str] | None = None,
) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "build_dir": str(build_dir),
        "bilbo_version": bilbo_version,
        "generated_files": generated_files,
    }
    if template_hashes:
        manifest["template_hashes_sha256"] = template_hashes
    out = build_dir / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out
