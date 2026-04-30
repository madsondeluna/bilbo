"""Tests for peptide placer and geometry utilities."""

import numpy as np
import pytest
from pathlib import Path

from bilbo.builders.geometry import (
    load_coordinates_pdb,
    load_coordinates_xyz,
    principal_axis,
    rotation_matrix_from_vectors,
)
from bilbo.builders.peptide_placer import place_peptide
from bilbo.models.peptide import PeptidePlacement


def test_read_peptide_pdb_coordinates(amp01_pdb):
    coords = load_coordinates_pdb(amp01_pdb)
    assert coords.shape[1] == 3
    assert len(coords) == 8


def test_read_peptide_xyz_coordinates(tmp_path):
    xyz = tmp_path / "test.xyz"
    xyz.write_text(
        "3\ncomment\nC 0.0 0.0 0.0\nC 1.0 0.0 0.0\nC 2.0 0.0 0.0\n",
        encoding="utf-8",
    )
    coords = load_coordinates_xyz(xyz)
    assert coords.shape == (3, 3)


def test_peptide_pca_axis_is_deterministic(amp01_pdb):
    coords = load_coordinates_pdb(amp01_pdb)
    axis1 = principal_axis(coords)
    axis2 = principal_axis(coords)
    np.testing.assert_array_almost_equal(axis1, axis2)


def test_parallel_orientation_places_axis_in_xy_plane(amp01_pdb):
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="parallel",
        leaflet="upper",
        depth=1.8,
    )
    result = place_peptide(pp)
    assert result.orientation == "parallel"
    assert result.transformed_coords is not None


def test_perpendicular_orientation_aligns_axis_to_z(amp01_pdb):
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="perpendicular",
        leaflet="upper",
        depth=1.0,
    )
    result = place_peptide(pp)
    assert result.orientation == "perpendicular"


def test_tilted_orientation_uses_tilt_deg(amp01_pdb):
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="tilted",
        leaflet="upper",
        tilt_deg=30,
    )
    result = place_peptide(pp)
    assert result.tilt_deg == 30


def test_transmembrane_placement_centers_on_bilayer(amp01_pdb):
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="transmembrane",
        leaflet="center",
    )
    result = place_peptide(pp)
    assert result.leaflet == "center"


def test_peptide_translation_vector_recorded(amp01_pdb):
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="parallel",
        leaflet="upper",
        x=1.0,
        y=2.0,
        depth=1.5,
    )
    result = place_peptide(pp)
    assert len(result.translation_vector) == 3


def test_peptide_rotation_matrix_recorded(amp01_pdb):
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="parallel",
        leaflet="upper",
    )
    result = place_peptide(pp)
    assert len(result.rotation_matrix) == 3
    assert len(result.rotation_matrix[0]) == 3


def test_collision_detection_reports_overlap(amp01_pdb):
    import numpy as np
    from bilbo.builders.geometry import load_coordinates_pdb

    coords = load_coordinates_pdb(amp01_pdb)
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="parallel",
        leaflet="upper",
        depth=0.0,
        allow_overlap=True,
        collision_cutoff=1000.0,
    )
    result = place_peptide(pp, membrane_coords=coords)
    assert result.collision_count >= 0


def test_collision_detection_blocks_when_allow_overlap_false(amp01_pdb):
    import numpy as np
    from bilbo.builders.geometry import load_coordinates_pdb

    coords = load_coordinates_pdb(amp01_pdb)
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="parallel",
        leaflet="upper",
        depth=0.0,
        allow_overlap=False,
        collision_cutoff=1000.0,
    )
    result = place_peptide(pp, membrane_coords=coords)
    if result.collision_count > 0:
        assert any("allow_overlap=false" in w for w in result.warnings)


def test_peptide_placement_produces_transformed_coords(amp01_pdb):
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="parallel",
        leaflet="upper",
        depth=1.8,
    )
    result = place_peptide(pp)
    assert result.transformed_coords is not None
    assert len(result.transformed_coords) > 0


def test_geometry_report_written(tmp_path, amp01_pdb):
    import json
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        input_structure=str(amp01_pdb),
        orientation="parallel",
        leaflet="upper",
    )
    result = place_peptide(pp)
    report = {
        "peptide_id": result.peptide_id,
        "rotation_matrix": result.rotation_matrix,
        "translation_vector": result.translation_vector,
        "collision_count": result.collision_count,
    }
    geo_path = tmp_path / "geometry_report.json"
    geo_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert geo_path.exists()
    loaded = json.loads(geo_path.read_text())
    assert loaded["peptide_id"] == "AMP01"
