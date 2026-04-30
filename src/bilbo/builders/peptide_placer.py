"""Geometric placement of peptides onto membrane previews."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from bilbo.builders.geometry import (
    count_collisions,
    load_coordinates_pdb,
    load_coordinates_xyz,
    principal_axis,
    rotation_matrix_from_vectors,
    rotation_matrix_x,
    rotation_matrix_z,
)
from bilbo.models.peptide import PeptidePlacement

UPPER_HEAD_Z_ANG = 20.0  # Angstrom
LOWER_HEAD_Z_ANG = -20.0
CENTER_Z_ANG = 0.0

LEAFLET_Z = {
    "upper": UPPER_HEAD_Z_ANG,
    "lower": LOWER_HEAD_Z_ANG,
    "center": CENTER_Z_ANG,
    "transmembrane": CENTER_Z_ANG,
}


@dataclass
class PlacementResult:
    peptide_id: str
    placement_id: str
    input_structure: str
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
    warnings: list[str] = field(default_factory=list)
    transformed_coords: Optional[np.ndarray] = field(default=None, repr=False)


def _load_coords(structure_file: str, structure_format: Optional[str] = None) -> np.ndarray:
    path = Path(structure_file)
    suffix = path.suffix.lower()
    if suffix == ".pdb" or structure_format == "pdb":
        return load_coordinates_pdb(path)
    if suffix == ".xyz" or structure_format == "xyz":
        return load_coordinates_xyz(path)
    raise ValueError(f"Cannot load structure: unsupported format '{suffix}'")


def _anchor_point(coords: np.ndarray, anchor_mode: str) -> np.ndarray:
    if anchor_mode == "center_of_mass":
        return coords.mean(axis=0)
    if anchor_mode == "n_terminus":
        return coords[0]
    if anchor_mode == "c_terminus":
        return coords[-1]
    return coords.mean(axis=0)


def place_peptide(
    placement: PeptidePlacement,
    membrane_coords: Optional[np.ndarray] = None,
    structure_file: Optional[str] = None,
    structure_format: Optional[str] = None,
) -> PlacementResult:
    src_file = structure_file or placement.input_structure
    if src_file is None:
        raise ValueError("structure_file or placement.input_structure must be set")

    coords = _load_coords(src_file, structure_format)
    warnings: list[str] = []

    com = coords.mean(axis=0)
    centered = coords - com

    axis = principal_axis(coords)
    z_axis = np.array([0.0, 0.0, 1.0])
    xy_axis = np.array([1.0, 0.0, 0.0])

    if placement.orientation == "parallel":
        target_axis = xy_axis
        rot = rotation_matrix_from_vectors(axis, target_axis)
    elif placement.orientation in ("perpendicular", "transmembrane"):
        target_axis = z_axis
        rot = rotation_matrix_from_vectors(axis, target_axis)
    elif placement.orientation == "tilted":
        target_axis = xy_axis
        rot = rotation_matrix_from_vectors(axis, target_axis)
        rot = rotation_matrix_x(placement.tilt_deg) @ rot
    else:
        rot = np.eye(3)

    rot = rotation_matrix_z(placement.azimuth_deg) @ rot
    rot = rotation_matrix_z(placement.rotation_deg) @ rot

    rotated = (rot @ centered.T).T

    target_z_ang = LEAFLET_Z.get(placement.leaflet, 0.0)
    depth_ang = placement.depth * 10.0 if placement.depth else 0.0

    z_offset = target_z_ang + depth_ang
    tx = placement.x * 10.0 if placement.x else 0.0
    ty = placement.y * 10.0 if placement.y else 0.0

    translation = np.array([tx, ty, z_offset])
    final_coords = rotated + translation

    collision_count = 0
    min_dist: Optional[float] = None
    if membrane_coords is not None:
        collision_count, min_dist = count_collisions(
            final_coords, membrane_coords, placement.collision_cutoff
        )
        if collision_count > 0:
            msg = (
                f"Peptide '{placement.peptide_id}': {collision_count} collision(s) "
                f"detected (min dist = {min_dist:.2f} A)."
            )
            warnings.append(msg)
            if not placement.allow_overlap:
                warnings.append("allow_overlap=false; build continues but collision is flagged.")

    return PlacementResult(
        peptide_id=placement.peptide_id,
        placement_id=placement.placement_id,
        input_structure=src_file,
        orientation=placement.orientation,
        leaflet=placement.leaflet,
        translation_vector=translation.tolist(),
        rotation_matrix=rot.tolist(),
        tilt_deg=placement.tilt_deg,
        rotation_deg=placement.rotation_deg,
        azimuth_deg=placement.azimuth_deg,
        anchor_mode=placement.anchor_mode,
        collision_count=collision_count,
        minimum_distance_to_membrane=min_dist,
        warnings=warnings,
        transformed_coords=final_coords,
    )
