"""Tests for leaflet layout builder."""

import pytest
from bilbo.builders.composition_expander import expand_composition
from bilbo.builders.leaflet_layout import build_leaflet_layout, save_leaflet_csv
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


def test_leaflet_layout_same_seed_same_output():
    preset = _ecoli_preset()
    expanded = expand_composition(preset, 64)
    l1 = build_leaflet_layout(expanded, "random", seed=42)
    l2 = build_leaflet_layout(expanded, "random", seed=42)
    p1 = [(p.x, p.y, p.lipid_id) for p in l1["upper"].positions]
    p2 = [(p.x, p.y, p.lipid_id) for p in l2["upper"].positions]
    assert p1 == p2


def test_leaflet_layout_different_seed_different_output():
    preset = _ecoli_preset()
    expanded = expand_composition(preset, 64)
    l1 = build_leaflet_layout(expanded, "random", seed=42)
    l2 = build_leaflet_layout(expanded, "random", seed=99)
    p1 = [p.lipid_id for p in l1["upper"].positions]
    p2 = [p.lipid_id for p in l2["upper"].positions]
    assert p1 != p2


def test_domain_enriched_groups_lipids():
    preset = _ecoli_preset()
    expanded = expand_composition(preset, 64)
    layouts = build_leaflet_layout(expanded, "domain_enriched", seed=42)
    upper = layouts["upper"]
    ids = [p.lipid_id for p in upper.positions]
    pope_indices = [i for i, lid in enumerate(ids) if lid == "POPE"]
    assert pope_indices == list(range(min(pope_indices), max(pope_indices) + 1))


def test_layout_csv_columns(tmp_path):
    preset = _ecoli_preset()
    expanded = expand_composition(preset, 16)
    layouts = build_leaflet_layout(expanded, "random", seed=1)
    csv_path = tmp_path / "upper_leaflet.csv"
    save_leaflet_csv(layouts["upper"], csv_path)
    lines = csv_path.read_text().strip().splitlines()
    assert lines[0] == "x,y,leaflet,lipid_id"
    assert len(lines) == 17
