"""BuildReport model."""

from typing import Optional

from pydantic import BaseModel


class PeptidePlacementRecord(BaseModel):
    peptide_id: str
    placement_id: str
    orientation: str
    leaflet: str
    translation_vector: list[float]
    rotation_matrix: list[list[float]]
    tilt_deg: float
    rotation_deg: float
    azimuth_deg: float
    anchor_mode: str
    collision_count: int
    minimum_distance_to_membrane: Optional[float]
    warnings: list[str] = []


class BuildReport(BaseModel):
    preset_id: str
    force_field: str
    engine: str
    lipids_per_leaflet: int
    sorting_mode: str
    seed: int
    desired_composition: dict[str, dict[str, float]]
    realized_composition: dict[str, dict[str, int]]
    rounding_errors: dict[str, dict[str, float]] = {}
    warnings: list[str] = []
    errors: list[str] = []
    generated_files: list[str] = []
    peptide_placements: list[PeptidePlacementRecord] = []
    geometry_warnings: list[str] = []
