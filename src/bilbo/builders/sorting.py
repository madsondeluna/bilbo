"""Sorting modes for lipid distribution in leaflets."""

import random
from typing import Literal

SortingMode = Literal["random", "domain_enriched"]


def sort_lipids(lipid_list: list[str], mode: SortingMode, seed: int) -> list[str]:
    rng = random.Random(seed)
    result = list(lipid_list)
    if mode == "random":
        rng.shuffle(result)
    elif mode == "domain_enriched":
        result = _domain_enriched(result, rng)
    return result


def _domain_enriched(lipid_list: list[str], rng: random.Random) -> list[str]:
    """Group identical lipids in approximate blocks (heuristic visual domain)."""
    groups: dict[str, list[str]] = {}
    for lid in lipid_list:
        groups.setdefault(lid, []).append(lid)

    group_keys = sorted(groups.keys())
    rng.shuffle(group_keys)

    result = []
    for key in group_keys:
        result.extend(groups[key])
    return result
