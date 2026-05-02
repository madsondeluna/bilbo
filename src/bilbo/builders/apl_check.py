"""Area-per-lipid reference data and bilayer composition balance checks."""

from __future__ import annotations

import math

from bilbo.models.preset import MembranePreset

# Reference area per lipid (A^2) at 303 K, liquid-crystalline (La) phase.
# Values from MD simulations validated against X-ray/neutron diffraction.
# Abbreviations used in source tags below:
#   [K11] Kucerka N et al. Biophys J. 2011;101:1828-1834. doi:10.1016/j.bpj.2011.08.009
#   [K10] Klauda JB et al. J Phys Chem B. 2010;114:7830-7843. doi:10.1021/jp101759q
#   [V14] Venable RM et al. J Chem Theory Comput. 2014;10:1397-1407. doi:10.1021/ct4010307
#   [P04] Mukhopadhyay P et al. Biophys J. 2004;86:1601-1609. doi:10.1016/S0006-3495(04)74227-7
#   [D07] Dahlberg M. J Phys Chem B. 2007;111:7194-7200. doi:10.1021/jp071954f
#         CL is counted as one molecule (two phosphate groups, four acyl chains).
APL_REFERENCE: dict[str, float] = {
    "DPPC": 64.3,   # [K11]
    "DMPC": 60.6,   # [K10]
    "DOPC": 72.5,   # [K11]
    "DOPE": 65.7,   # [V14]
    "POPE": 56.6,   # [K11]
    "POPC": 68.3,   # [K11]
    "POPG": 65.0,   # [V14]
    "POPS": 55.5,   # [P04]
    "CL":  130.0,   # [D07]
    "TOCL":130.0,   # [D07] (tetraoleoyl cardiolipin analogue)
}

_MISMATCH_WARN_PCT = 10.0


def weighted_spacing(
    counts_by_leaflet: dict[str, dict[str, int]],
) -> float | None:
    """Return grid spacing (nm) from composition-weighted mean APL.

    Returns None when any lipid species is absent from APL_REFERENCE.
    Spacing = sqrt(mean_APL) converted from Angstroms to nm.
    """
    total_n = 0
    total_apl = 0.0
    for counts in counts_by_leaflet.values():
        for lid, n in counts.items():
            apl = APL_REFERENCE.get(lid.upper())
            if apl is None:
                return None
            total_n += n
            total_apl += n * apl
    if total_n == 0:
        return None
    return math.sqrt(total_apl / total_n) / 10.0  # A -> nm


def check_apl_balance(preset: MembranePreset, lipids_per_leaflet: int) -> list[str]:
    """Return warnings about APL imbalance between leaflets.

    For asymmetric membranes: compares total projected area of each leaflet
    (lipids_per_leaflet * weighted-mean APL). A mismatch above 10% means
    the two leaflets have incompatible footprints at equal lipid count, which
    generates lateral membrane stress in simulation.

    If any lipid in either leaflet is absent from APL_REFERENCE the area
    comparison is skipped entirely (partial APL cannot be meaningfully compared).
    Only the "unknown lipid" advisory is emitted in that case.
    """
    warnings: list[str] = []
    upper_comp = preset.leaflets.get("upper", {})
    lower_comp = preset.leaflets.get("lower", {})

    upper_unknown = [lid for lid in upper_comp if lid.upper() not in APL_REFERENCE]
    lower_unknown = [lid for lid in lower_comp if lid.upper() not in APL_REFERENCE]
    all_unknown = list(dict.fromkeys(upper_unknown + lower_unknown))

    if all_unknown:
        warnings.append(
            f"APL reference missing for: {', '.join(all_unknown)}. "
            "Leaflet area balance check requires all lipids to be in the reference table "
            "(src/bilbo/builders/apl_check.py); skipping comparison."
        )
        return warnings

    def _weighted_apl(comp: dict[str, float]) -> float:
        total = sum(comp.values())
        return sum((pct / total) * APL_REFERENCE[lid.upper()] for lid, pct in comp.items())

    upper_apl = _weighted_apl(upper_comp)
    lower_apl = _weighted_apl(lower_comp)

    if upper_apl <= 0 or lower_apl <= 0:
        return warnings

    upper_area = lipids_per_leaflet * upper_apl
    lower_area = lipids_per_leaflet * lower_apl
    mismatch_pct = abs(upper_area - lower_area) / max(upper_area, lower_area) * 100.0

    if mismatch_pct > _MISMATCH_WARN_PCT:
        larger = "upper" if upper_apl > lower_apl else "lower"
        smaller_apl = lower_apl if upper_apl > lower_apl else upper_apl
        larger_area = max(upper_area, lower_area)
        n_adjusted = round(larger_area / smaller_apl) if smaller_apl > 0 else lipids_per_leaflet
        smaller_leaflet = "lower" if upper_apl > lower_apl else "upper"
        warnings.append(
            f"Leaflet area mismatch: {mismatch_pct:.1f}% "
            f"(upper {upper_apl:.1f} A^2/lipid x {lipids_per_leaflet} = {upper_area:.0f} A^2; "
            f"lower {lower_apl:.1f} A^2/lipid x {lipids_per_leaflet} = {lower_area:.0f} A^2). "
            f"The {larger} leaflet has a larger projected area. "
            f"To equalize tension, use {n_adjusted} lipids for the {smaller_leaflet} leaflet "
            f"instead of {lipids_per_leaflet}."
        )

    return warnings
