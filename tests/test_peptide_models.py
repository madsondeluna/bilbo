"""Tests for Peptide and PeptidePlacement models."""

import pytest
from pydantic import ValidationError

from bilbo.models.peptide import Peptide, PeptidePlacement


def test_valid_peptide_metadata():
    pep = Peptide(id="AMP01", name="Test peptide", sequence="ALIKKAILL")
    assert pep.id == "AMP01"
    assert pep.sequence == "ALIKKAILL"


def test_reject_peptide_without_id():
    with pytest.raises(ValidationError):
        Peptide(id="", name="bad")


def test_peptide_placement_tilt_validation():
    with pytest.raises(ValidationError):
        PeptidePlacement(
            peptide_id="AMP01",
            placement_id="p1",
            tilt_deg=200,
        )


def test_peptide_placement_valid():
    pp = PeptidePlacement(
        peptide_id="AMP01",
        placement_id="p1",
        orientation="parallel",
        leaflet="upper",
        tilt_deg=0,
        rotation_deg=90,
        azimuth_deg=0,
    )
    assert pp.orientation == "parallel"
