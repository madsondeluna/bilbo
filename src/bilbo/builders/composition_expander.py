"""Convert percentage-based leaflet compositions to integer lipid counts."""

from dataclasses import dataclass

from bilbo.models.preset import MembranePreset


@dataclass
class ExpandedComposition:
    leaflet: str
    counts: dict[str, int]
    rounding_errors: dict[str, float]

    def total(self) -> int:
        return sum(self.counts.values())


def _largest_remainder(
    percentages: dict[str, float], total: int
) -> tuple[dict[str, int], dict[str, float]]:
    """Distribute `total` slots using the largest-remainder method.

    Ties in remainder are broken by lipid_id ascending for determinism.
    """
    raw = {lid: pct / 100.0 * total for lid, pct in percentages.items()}
    floors = {lid: int(v) for lid, v in raw.items()}
    remainders = {lid: raw[lid] - floors[lid] for lid in raw}

    deficit = total - sum(floors.values())
    sorted_by_remainder = sorted(
        remainders.keys(), key=lambda lid: (-remainders[lid], lid)
    )
    for lid in sorted_by_remainder[:deficit]:
        floors[lid] += 1

    rounding_errors = {lid: floors[lid] - raw[lid] for lid in raw}
    return floors, rounding_errors


def expand_composition(
    preset: MembranePreset, lipids_per_leaflet: int
) -> list[ExpandedComposition]:
    results = []
    for leaflet_name, comp in preset.leaflets.items():
        counts, errors = _largest_remainder(comp, lipids_per_leaflet)
        results.append(
            ExpandedComposition(
                leaflet=leaflet_name,
                counts=counts,
                rounding_errors=errors,
            )
        )
    return results
