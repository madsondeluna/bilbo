"""Extract Reference objects from YAML, JSON, or simple BibTeX-like records."""

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from bilbo.extractors.base import BaseExtractor
from bilbo.models.reference import Reference


def _load_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    if path.suffix == ".json":
        return json.loads(text)
    raise ValueError(f"Unsupported reference format: {path.suffix}")


class ReferenceMetadataExtractor(BaseExtractor):
    def extract(self, path: Path) -> list[Reference]:
        path = Path(path)
        if path.is_dir():
            refs: list[Reference] = []
            for f in sorted(path.iterdir()):
                if f.suffix in (".yaml", ".yml", ".json"):
                    refs.extend(self._extract_file(f))
            return refs
        return self._extract_file(path)

    def _extract_file(self, path: Path) -> list[Reference]:
        data = _load_file(path)
        results = []
        items = data if isinstance(data, list) else [data]
        for item in items:
            try:
                results.append(Reference.model_validate(item))
            except ValidationError as exc:
                raise ValueError(f"Invalid reference in {path}:\n{exc}") from exc
        return results
