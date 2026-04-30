"""Scan local topology files for residue names."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from bilbo.extractors.base import BaseExtractor

TOPOLOGY_EXTENSIONS = {".itp", ".top", ".rtf", ".prm", ".str"}
MOLECULETYPE_RE = re.compile(r"^\[\s*moleculetype\s*\]", re.IGNORECASE)
RESIDUE_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s+\d+\s*$")
RESI_RE = re.compile(r"^\s*(?:RESI|RESIDUE)\s+([A-Za-z0-9_]+)", re.IGNORECASE)


@dataclass
class TopologyScanResult:
    found_residues: set[str] = field(default_factory=set)
    missing_residues: set[str] = field(default_factory=set)
    topology_files_scanned: list[str] = field(default_factory=list)


def _extract_residues_from_itp_top(text: str) -> set[str]:
    """Extract residue/molecule names from GROMACS .itp/.top files."""
    residues: set[str] = set()
    in_moleculetype = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(";"):
            continue
        if MOLECULETYPE_RE.match(stripped):
            in_moleculetype = True
            continue
        if in_moleculetype:
            if stripped.startswith("["):
                in_moleculetype = False
                continue
            m = RESIDUE_LINE_RE.match(stripped)
            if m:
                residues.add(m.group(1))
    return residues


def _extract_residues_from_charmm(text: str) -> set[str]:
    """Extract residue names from CHARMM .rtf/.str files."""
    residues: set[str] = set()
    for line in text.splitlines():
        m = RESI_RE.match(line)
        if m:
            residues.add(m.group(1))
    return residues


def _extract_residues_from_file(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix in (".itp", ".top"):
        return _extract_residues_from_itp_top(text)
    if path.suffix in (".rtf", ".str", ".prm"):
        return _extract_residues_from_charmm(text)
    return set()


class TopologyScanner(BaseExtractor):
    def extract(self, path: Path) -> TopologyScanResult:
        return self.scan(path, residues_to_check=None)

    def scan(
        self,
        path: Path,
        residues_to_check: list[str] | None = None,
    ) -> TopologyScanResult:
        path = Path(path)
        result = TopologyScanResult()

        files = []
        if path.is_dir():
            for ext in TOPOLOGY_EXTENSIONS:
                files.extend(path.rglob(f"*{ext}"))
        elif path.suffix in TOPOLOGY_EXTENSIONS:
            files = [path]

        all_residues: set[str] = set()
        for f in files:
            result.topology_files_scanned.append(str(f))
            all_residues |= _extract_residues_from_file(f)

        result.found_residues = all_residues

        if residues_to_check:
            for name in residues_to_check:
                if name in all_residues:
                    result.found_residues.add(name)
                else:
                    result.missing_residues.add(name)

        return result
