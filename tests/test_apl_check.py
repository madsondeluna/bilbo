"""Tests for APL balance check."""

import pytest
from bilbo.builders.apl_check import check_apl_balance, APL_REFERENCE
from bilbo.models.preset import MembranePreset


def _preset(upper: dict, lower: dict, sym: str = "asymmetric") -> MembranePreset:
    return MembranePreset(
        id="test",
        symmetry=sym,
        leaflets={"upper": upper, "lower": lower},
    )


def test_symmetric_no_warning():
    p = _preset({"POPE": 70, "POPG": 30}, {"POPE": 70, "POPG": 30}, sym="symmetric")
    warns = check_apl_balance(p, 128)
    assert warns == []


def test_symmetric_small_diff_no_warning():
    # POPE (56.6) and POPG (65.0): upper-weighted vs lower-weighted differ but same leaflet
    p = _preset({"POPE": 70, "POPG": 30}, {"POPE": 70, "POPG": 30}, sym="symmetric")
    warns = check_apl_balance(p, 64)
    assert warns == []


def test_asymmetric_large_mismatch_warns():
    # Upper: all DOPC (72.5), lower: all POPE (56.6)
    # mismatch = (72.5 - 56.6) / 72.5 * 100 = ~21.9%  -> should warn
    p = _preset({"DOPC": 100}, {"POPE": 100})
    warns = check_apl_balance(p, 128)
    assert len(warns) == 1
    assert "mismatch" in warns[0].lower()
    assert "21." in warns[0]


def test_asymmetric_small_mismatch_no_warning():
    # Upper: all POPC (68.3), lower: all POPG (65.0)
    # mismatch = (68.3 - 65.0) / 68.3 * 100 = ~4.8%  -> below threshold
    p = _preset({"POPC": 100}, {"POPG": 100})
    warns = check_apl_balance(p, 128)
    assert warns == []


def test_unknown_lipid_skips_comparison():
    p = _preset({"DOPC": 100}, {"UNKN": 100})
    warns = check_apl_balance(p, 128)
    assert len(warns) == 1
    assert "UNKN" in warns[0]
    assert "skipping" in warns[0].lower()


def test_unknown_lipid_in_both_leaflets():
    p = _preset({"UNKNA": 50, "POPE": 50}, {"UNKNB": 100})
    warns = check_apl_balance(p, 64)
    assert any("UNKNA" in w or "UNKNB" in w for w in warns)
    # No area comparison warning should appear
    assert not any("mismatch" in w.lower() for w in warns)


def test_adjusted_count_in_warning():
    # Upper: DOPC (72.5 A^2) x 128 = 9280 A^2
    # Lower: POPE (56.6 A^2) -> adjusted = round(9280 / 56.6) = 164
    p = _preset({"DOPC": 100}, {"POPE": 100})
    warns = check_apl_balance(p, 128)
    assert "164" in warns[0]


def test_apl_reference_values_positive():
    for lid, apl in APL_REFERENCE.items():
        assert apl > 0, f"APL for {lid} must be positive"
        assert apl < 300, f"APL for {lid} ({apl}) exceeds plausible range"


def test_apl_source_file_has_doi_citations():
    import inspect
    import bilbo.builders.apl_check as m
    src = inspect.getsource(m)
    assert "doi:" in src.lower(), "APL reference table must include doi citations in source"
