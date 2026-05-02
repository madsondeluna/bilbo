"""Generate 2D grid layout for leaflets."""

import math
from dataclasses import dataclass
from pathlib import Path

from bilbo.builders.composition_expander import ExpandedComposition
from bilbo.builders.sorting import SortingMode, sort_lipids


@dataclass
class LipidPosition:
    x: float
    y: float
    leaflet: str
    lipid_id: str


@dataclass
class LeafletLayout:
    positions: list[LipidPosition]
    grid_nx: int
    grid_ny: int
    spacing: float

    def box_x(self) -> float:
        return self.grid_nx * self.spacing

    def box_y(self) -> float:
        return self.grid_ny * self.spacing


def _make_lipid_list(counts: dict[str, int]) -> list[str]:
    lipids = []
    for lid, n in sorted(counts.items()):
        lipids.extend([lid] * n)
    return lipids


def build_leaflet_layout(
    expanded: list[ExpandedComposition],
    sorting_mode: SortingMode,
    seed: int,
    spacing: float = 0.7,
) -> dict[str, LeafletLayout]:
    layouts: dict[str, LeafletLayout] = {}

    for ec in expanded:
        lipid_list = _make_lipid_list(ec.counts)
        n = len(lipid_list)

        nx = math.ceil(math.sqrt(n))
        ny = math.ceil(n / nx)

        sorted_list = sort_lipids(lipid_list, sorting_mode, seed, nx=nx)

        positions = []
        for i, lid in enumerate(sorted_list):
            col = i % nx
            row = i // nx
            x = col * spacing + spacing / 2
            y = row * spacing + spacing / 2
            positions.append(LipidPosition(x=x, y=y, leaflet=ec.leaflet, lipid_id=lid))

        layouts[ec.leaflet] = LeafletLayout(
            positions=positions,
            grid_nx=nx,
            grid_ny=ny,
            spacing=spacing,
        )

    return layouts


def save_leaflet_csv(layout: LeafletLayout, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write("x,y,leaflet,lipid_id\n")
        for pos in layout.positions:
            fh.write(f"{pos.x:.4f},{pos.y:.4f},{pos.leaflet},{pos.lipid_id}\n")
