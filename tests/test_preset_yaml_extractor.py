"""Tests for preset YAML extractor."""

import pytest
from pathlib import Path

from bilbo.extractors.preset_yaml import PresetYAMLExtractor


def test_extract_single_preset_yaml(ecoli_preset_yaml):
    extractor = PresetYAMLExtractor()
    presets = extractor.extract(ecoli_preset_yaml)
    assert len(presets) == 1
    p = presets[0]
    assert p.id == "ecoli_inner_membrane_default"
    assert "upper" in p.leaflets
    assert "lower" in p.leaflets


def test_extract_preset_directory(preset_yaml_dir):
    extractor = PresetYAMLExtractor()
    presets = extractor.extract(preset_yaml_dir)
    ids = [p.id for p in presets]
    assert "ecoli_inner_membrane_default" in ids
    assert len(presets) >= 1
