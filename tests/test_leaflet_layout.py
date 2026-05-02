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


def test_stripe_alternating_bands():
    preset = _ecoli_preset()
    expanded = expand_composition(preset, 64)
    layouts = build_leaflet_layout(expanded, "stripe", seed=42)
    upper = layouts["upper"]
    nx = upper.grid_nx
    ids = [p.lipid_id for p in upper.positions]

    # Collect distinct species per row
    ny = upper.grid_ny
    row_species = []
    for row in range(ny):
        row_ids = ids[row * nx : (row + 1) * nx]
        dominant = max(set(row_ids), key=row_ids.count) if row_ids else None
        row_species.append(dominant)

    # At least two distinct species must appear across rows
    assert len(set(row_species)) >= 2

    # Species must not be identical in all consecutive pairs (i.e. banding changes)
    consecutive_same = sum(1 for a, b in zip(row_species, row_species[1:]) if a == b)
    total_pairs = len(row_species) - 1
    assert consecutive_same < total_pairs


def test_layout_csv_columns(tmp_path):
    preset = _ecoli_preset()
    expanded = expand_composition(preset, 16)
    layouts = build_leaflet_layout(expanded, "random", seed=1)
    csv_path = tmp_path / "upper_leaflet.csv"
    save_leaflet_csv(layouts["upper"], csv_path)
    lines = csv_path.read_text().strip().splitlines()
    assert lines[0] == "x,y,leaflet,lipid_id"
    assert len(lines) == 17
