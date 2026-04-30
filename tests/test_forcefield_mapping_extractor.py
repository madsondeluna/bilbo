"""Tests for force field mapping extractor."""

import pytest
from pathlib import Path
import tempfile

from bilbo.extractors.forcefield_mapping import ForceFieldMappingExtractor


def test_extract_forcefield_mapping_csv(forcefield_csv):
    extractor = ForceFieldMappingExtractor()
    mappings = extractor.extract(forcefield_csv)
    ids = [m.lipid_id for m in mappings]
    assert "POPC" in ids
    assert "CHOL" in ids
    assert len(mappings) >= 6
    for m in mappings:
        assert m.force_field == "charmm36"


def test_extract_forcefield_mapping_tsv(tmp_path):
    tsv = tmp_path / "test.tsv"
    tsv.write_text(
        "lipid_id\tforce_field\tresidue_name\ttopology_file\tstatus\tnotes\n"
        "POPC\tcharmm36\tPOPC\ttest.itp\tvalidated\tnote\n",
        encoding="utf-8",
    )
    extractor = ForceFieldMappingExtractor()
    mappings = extractor.extract(tsv)
    assert len(mappings) == 1
    assert mappings[0].lipid_id == "POPC"
