"""Tests for lipid YAML extractor."""

import pytest
from pathlib import Path

from bilbo.extractors.lipid_yaml import LipidYAMLExtractor


def test_extract_single_lipid_yaml(popc_yaml):
    extractor = LipidYAMLExtractor()
    lipids = extractor.extract(popc_yaml)
    assert len(lipids) == 1
    assert lipids[0].id == "POPC"
    assert lipids[0].curation_status == "validated"


def test_extract_lipid_directory(lipid_yaml_dir):
    extractor = LipidYAMLExtractor()
    lipids = extractor.extract(lipid_yaml_dir)
    ids = [l.id for l in lipids]
    assert "POPC" in ids
    assert "POPE" in ids
    assert "CL" in ids
    assert len(lipids) >= 6
