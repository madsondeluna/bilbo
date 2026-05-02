"""Sorting modes for lipid distribution in leaflets."""

import math
import random
from collections import Counter
from typing import Literal

SortingMode = Literal["random", "domain_enriched", "stripe"]


def sort_lipids(lipid_list: list[str], mode: SortingMode, seed: int, nx: int = 1) -> list[str]:
    rng = random.Random(seed)
    result = list(lipid_list)
    if mode == "random":
        rng.shuffle(result)
    elif mode == "domain_enriched":
        result = _domain_enriched(result, rng)
    elif mode == "stripe":
        result = _stripe(result, nx, rng)
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


def _proportional_rows(species: list[str], counts: dict[str, int], ny: int) -> dict[str, int]:
    """Allocate grid rows to species proportionally (Hamilton largest-remainder method)."""
    total = sum(counts[sp] for sp in species)
    n = len(species)
    raw = {sp: counts[sp] / total * ny for sp in species}
    alloc = {sp: max(1, int(raw[sp])) for sp in species}
    diff = ny - sum(alloc.values())
    if diff > 0:
        order = sorted(species, key=lambda sp: raw[sp] - int(raw[sp]), reverse=True)
        for i in range(diff):
            alloc[order[i % n]] += 1
    elif diff < 0:
        order = sorted(species, key=lambda sp: raw[sp] - int(raw[sp]))
        for i in range(-diff):
            sp = order[i % n]
            if alloc[sp] > 1:
                alloc[sp] -= 1
    return alloc


def _stripe(lipid_list: list[str], nx: int, rng: random.Random) -> list[str]:
    """Arrange lipids in alternating horizontal bands (A-B-A-B row pattern)."""
    counts = dict(Counter(lipid_list))
    n = len(lipid_list)
    ny = math.ceil(n / nx)

    species = sorted(counts.keys(), key=lambda k: (-counts[k], k))
    row_alloc = _proportional_rows(species, counts, ny)

    # Build row sequence by round-robin interleaving each species' allocated rows
    # into bands of 1 row each, cycling through species: A B C A B C ...
    row_sequence: list[tuple[str, int]] = []
    remaining_rows = {sp: row_alloc[sp] for sp in species}
    n_species = len(species)
    while any(v > 0 for v in remaining_rows.values()):
        for sp in species:
            if remaining_rows[sp] > 0:
                row_sequence.append((sp, 1))
                remaining_rows[sp] -= 1

    sp_pool = dict(counts)
    result: list[str] = []
    for sp, _ in row_sequence:
        avail = sp_pool.get(sp, 0)
        fill = min(nx, avail)
        result.extend([sp] * fill)
        sp_pool[sp] = avail - fill
        # fill remainder of row from other species if needed
        shortage = nx - fill
        for other in species:
            if shortage <= 0:
                break
            avail_other = sp_pool.get(other, 0)
            if avail_other > 0:
                take = min(shortage, avail_other)
                result.extend([other] * take)
                sp_pool[other] = avail_other - take
                shortage -= take

    return result[:n]
