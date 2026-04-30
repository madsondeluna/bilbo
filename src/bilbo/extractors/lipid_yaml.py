"""Extract Lipid objects from YAML or JSON files."""

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from bilbo.extractors.base import BaseExtractor
from bilbo.models.lipid import Lipid


def _load_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    if path.suffix == ".json":
        return json.loads(text)
    raise ValueError(f"Unsupported file format: {path.suffix}")


def _parse_lipid(data: Any, source_path: Path) -> Lipid:
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping at {source_path}, got {type(data).__name__}")
    try:
        return Lipid.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid lipid in {source_path}:\n{exc}") from exc


class LipidYAMLExtractor(BaseExtractor):
    def extract(self, path: Path) -> list[Lipid]:
        path = Path(path)
        if path.is_dir():
            lipids = []
            for f in sorted(path.iterdir()):
                if f.suffix in (".yaml", ".yml", ".json") and not f.name.startswith("._"):
                    lipids.extend(self._extract_file(f))
            return lipids
        return self._extract_file(path)

    def _extract_file(self, path: Path) -> list[Lipid]:
        data = _load_file(path)
        if isinstance(data, list):
            return [_parse_lipid(item, path) for item in data]
        return [_parse_lipid(data, path)]
