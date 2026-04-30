"""Tests for composition expander."""

import pytest
from bilbo.builders.composition_expander import expand_composition
from bilbo.models.preset import MembranePreset
from bilbo.models.reference import Reference


def _ecoli_preset():
    return MembranePreset(
        id="ecoli",
        leaflets={
            "upper": {"POPE": 70, "POPG": 20, "CL": 10},
            "lower": {"POPE": 70, "POPG": 20, "CL": 10},
        },
        references=[Reference(id="r1", manual_citation="test")],
    )


def test_composition_expander_preserves_total_upper():
    preset = _ecoli_preset()
    expanded = expand_composition(preset, 64)
    upper = next(e for e in expanded if e.leaflet == "upper")
    assert upper.total() == 64


def test_composition_expander_preserves_total_lower():
    preset = _ecoli_preset()
    expanded = expand_composition(preset, 64)
    lower = next(e for e in expanded if e.leaflet == "lower")
    assert lower.total() == 64


def test_composition_expander_deterministic_rounding():
    preset = _ecoli_preset()
    e1 = expand_composition(preset, 64)
    e2 = expand_composition(preset, 64)
    for a, b in zip(e1, e2):
        assert a.counts == b.counts


def test_composition_expander_approximate_counts():
    preset = _ecoli_preset()
    expanded = expand_composition(preset, 64)
    upper = next(e for e in expanded if e.leaflet == "upper")
    assert upper.counts["POPE"] == 45
    assert upper.counts["POPG"] == 13
    assert upper.counts["CL"] == 6
