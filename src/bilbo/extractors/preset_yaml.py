"""Extract MembranePreset objects from YAML or JSON files."""

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from bilbo.extractors.base import BaseExtractor
from bilbo.models.preset import MembranePreset


def _load_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    if path.suffix == ".json":
        return json.loads(text)
    raise ValueError(f"Unsupported file format: {path.suffix}")


def _parse_preset(data: Any, source_path: Path) -> MembranePreset:
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping at {source_path}, got {type(data).__name__}")
    try:
        return MembranePreset.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid preset in {source_path}:\n{exc}") from exc


class PresetYAMLExtractor(BaseExtractor):
    def extract(self, path: Path) -> list[MembranePreset]:
        path = Path(path)
        if path.is_dir():
            presets = []
            for f in sorted(path.iterdir()):
                if f.suffix in (".yaml", ".yml", ".json") and not f.name.startswith("._"):
                    presets.extend(self._extract_file(f))
            return presets
        return self._extract_file(path)

    def _extract_file(self, path: Path) -> list[MembranePreset]:
        data = _load_file(path)
        if isinstance(data, list):
            return [_parse_preset(item, path) for item in data]
        return [_parse_preset(data, path)]
