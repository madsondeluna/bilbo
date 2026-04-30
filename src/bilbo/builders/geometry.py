"""Geometric utilities for peptide placement."""

import math
from pathlib import Path

import numpy as np


def load_coordinates_pdb(path: Path) -> np.ndarray:
    """Return Nx3 array of atom coordinates from a PDB file (in Angstrom)."""
    coords = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(("ATOM", "HETATM")):
            try:
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
                coords.append([x, y, z])
            except ValueError:
                continue
    if not coords:
        raise ValueError(f"No ATOM/HETATM records found in {path}")
    return np.array(coords, dtype=float)


def load_coordinates_xyz(path: Path) -> np.ndarray:
    """Return Nx3 array of atom coordinates from an XYZ file."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if len(lines) < 3:
        raise ValueError(f"XYZ file too short: {path}")
    n_atoms = int(lines[0].strip())
    coords = []
    for line in lines[2 : 2 + n_atoms]:
        parts = line.split()
        if len(parts) >= 4:
            coords.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return np.array(coords, dtype=float)


def principal_axis(coords: np.ndarray) -> np.ndarray:
    """Return the principal axis (largest variance) of a set of coordinates.

    Centers coords on centroid, then uses SVD. The sign is fixed so that
    the first non-zero component of the axis is positive (deterministic).
    """
    centroid = coords.mean(axis=0)
    centered = coords - centroid
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    axis = vt[0]
    first_nonzero = next((v for v in axis if abs(v) > 1e-9), None)
    if first_nonzero is not None and first_nonzero < 0:
        axis = -axis
    return axis


def rotation_matrix_from_vectors(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Rotation matrix that rotates unit vector src onto unit vector dst."""
    src = src / np.linalg.norm(src)
    dst = dst / np.linalg.norm(dst)
    v = np.cross(src, dst)
    c = np.dot(src, dst)
    if abs(c + 1.0) < 1e-9:
        perp = np.array([1.0, 0.0, 0.0]) if abs(src[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        v = np.cross(src, perp)
        v /= np.linalg.norm(v)
        return 2.0 * np.outer(v, v) - np.eye(3)
    s = np.linalg.norm(v)
    kmat = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + kmat + kmat @ kmat * ((1 - c) / (s * s + 1e-30))


def rotation_matrix_z(angle_deg: float) -> np.ndarray:
    a = math.radians(angle_deg)
    return np.array([
        [math.cos(a), -math.sin(a), 0],
        [math.sin(a), math.cos(a), 0],
        [0, 0, 1],
    ])


def rotation_matrix_x(angle_deg: float) -> np.ndarray:
    a = math.radians(angle_deg)
    return np.array([
        [1, 0, 0],
        [0, math.cos(a), -math.sin(a)],
        [0, math.sin(a), math.cos(a)],
    ])


def apply_rotation_translation(
    coords: np.ndarray, rot: np.ndarray, translation: np.ndarray
) -> np.ndarray:
    return (rot @ coords.T).T + translation


def count_collisions(
    peptide_coords: np.ndarray, membrane_coords: np.ndarray, cutoff: float
) -> tuple[int, float]:
    """Return (collision_count, minimum_distance).

    Uses brute-force pairwise distance; fine for preview pseudoatom counts.
    """
    if len(peptide_coords) == 0 or len(membrane_coords) == 0:
        return 0, float("inf")

    diff = peptide_coords[:, None, :] - membrane_coords[None, :, :]
    dists = np.sqrt((diff ** 2).sum(axis=-1))
    min_dist = float(dists.min())
    collisions = int((dists < cutoff).any(axis=1).sum())
    return collisions, min_dist
