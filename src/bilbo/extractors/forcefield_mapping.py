"""Extract ForceFieldMapping objects from CSV or TSV files."""

import csv
from pathlib import Path

from bilbo.extractors.base import BaseExtractor
from bilbo.models.forcefield import ForceFieldMapping


class ForceFieldMappingExtractor(BaseExtractor):
    def extract(self, path: Path) -> list[ForceFieldMapping]:
        path = Path(path)
        if path.is_dir():
            mappings = []
            for f in sorted(path.iterdir()):
                if f.suffix in (".csv", ".tsv"):
                    mappings.extend(self._extract_file(f))
            return mappings
        return self._extract_file(path)

    def _extract_file(self, path: Path) -> list[ForceFieldMapping]:
        delimiter = "\t" if path.suffix == ".tsv" else ","
        mappings = []
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            for i, row in enumerate(reader, start=2):
                row = {k.strip(): (v.strip() if v else "") for k, v in row.items()}
                try:
                    mappings.append(
                        ForceFieldMapping(
                            lipid_id=row["lipid_id"],
                            force_field=row["force_field"],
                            residue_name=row["residue_name"],
                            topology_file=row.get("topology_file") or None,
                            status=row.get("status", "requires_mapping_check"),
                            notes=row.get("notes") or None,
                        )
                    )
                except (KeyError, ValueError) as exc:
                    raise ValueError(f"Error on row {i} of {path}: {exc}") from exc
        return mappings
