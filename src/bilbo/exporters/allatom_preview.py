"""Export all-atom membrane preview by tiling lipid PDB templates."""

import math
import random
from pathlib import Path

import numpy as np

from bilbo.builders.leaflet_layout import LeafletLayout

_CHAIN = {"upper": "U", "lower": "L"}

# Half the inter-leaflet gap (Angstroms). Tails of the upper leaflet end at
# +_Z_TAIL and tails of the lower leaflet end at -_Z_TAIL, giving a 2*_Z_TAIL
# gap at the bilayer center. 6 A total is a clash-avoidance buffer chosen so
# that tail-terminal atoms of opposing leaflets do not overlap in an
# unminimized template-tiled structure. It is not derived from experimental
# bilayer thickness data; the user must run energy minimization before
# interpreting inter-leaflet distances.
_Z_TAIL = 3.0


def _load_template(pdb_path: Path) -> list[str]:
    lines = []
    for line in pdb_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(("ATOM", "HETATM")):
            lines.append(line)
    return lines


def _template_z_tail(atom_lines: list[str]) -> float:
    """Return the minimum z coordinate in the template (tail end)."""
    return min(float(line[46:54]) for line in atom_lines)


def _template_xy_centroid(atom_lines: list[str]) -> tuple[float, float]:
    """Return the mean XY position of all template atoms."""
    xs = [float(line[30:38]) for line in atom_lines]
    ys = [float(line[38:46]) for line in atom_lines]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _place_atoms(
    atom_lines: list[str],
    cx: float,
    cy: float,
    centroid_x: float,
    centroid_y: float,
    theta: float,
    z_flip: float,
    chain: str,
    resseq: int,
    z_tail: float,
    z_half_gap: float = _Z_TAIL,
    tilt_angle_rad: float = 0.0,
    tilt_phi: float = 0.0,
) -> list[str]:
    """Rotate each lipid azimuthally around Z, then translate to (cx, cy).

    Each atom is shifted relative to the template XY centroid, rotated by
    theta around the membrane normal (Z axis), and placed so the centroid
    lands at (cx, cy). Z is normalized so the tail end sits at z_half_gap
    from the bilayer center, with z_flip = +1 for upper and -1 for lower.
    """
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    out = []
    for line in atom_lines:
        x0 = float(line[30:38]) - centroid_x
        y0 = float(line[38:46]) - centroid_y
        z0 = float(line[46:54])
        x = cos_t * x0 - sin_t * y0 + cx
        y = sin_t * x0 + cos_t * y0 + cy
        z_norm = z0 - z_tail + z_half_gap
        z = z_flip * z_norm
        if tilt_angle_rad != 0.0:
            cos_a = math.cos(tilt_angle_rad)
            sin_a = math.sin(tilt_angle_rad)
            ax = math.cos(tilt_phi)
            ay = math.sin(tilt_phi)
            xr = x - cx
            yr = y - cy
            x = xr * (cos_a + ax * ax * (1 - cos_a)) + yr * (ax * ay * (1 - cos_a)) + z * (ay * sin_a) + cx
            y = xr * (ax * ay * (1 - cos_a)) + yr * (cos_a + ay * ay * (1 - cos_a)) + z * (-ax * sin_a) + cy
            z = xr * (-ay * sin_a) + yr * (ax * sin_a) + z * cos_a
        record = (
            line[:21]
            + chain
            + f"{resseq:4d}"
            + line[26:30]
            + f"{x:8.3f}{y:8.3f}{z:8.3f}"
            + line[54:]
        )
        out.append(record)
    return out


def _check_inter_species_clashes(
    all_lines: list[str],
    resid_to_lipid: dict[int, str],
    threshold: float,
) -> list[str]:
    """Detect inter-species atom clashes and return warning strings.

    Uses a 3D bounding-box pre-filter (correctly separates the two leaflets
    whose Z ranges are non-overlapping) before doing full pairwise checks
    only on candidate residue pairs.
    """
    if len(all_lines) < 2:
        return []

    from collections import defaultdict

    res_coords: dict[int, list] = defaultdict(list)
    for line in all_lines:
        resid = int(line[22:26])
        x = float(line[30:38])
        y = float(line[38:46])
        z = float(line[46:54])
        res_coords[resid].append([x, y, z])

    res_ids = sorted(res_coords.keys())
    res_arrays = {r: np.array(v) for r, v in res_coords.items()}
    res_mins = {r: a.min(axis=0) for r, a in res_arrays.items()}
    res_maxs = {r: a.max(axis=0) for r, a in res_arrays.items()}

    clash_pairs: list[tuple[int, int, str, str, float]] = []
    for i, r1 in enumerate(res_ids):
        l1 = resid_to_lipid.get(r1, "")
        mn1, mx1 = res_mins[r1], res_maxs[r1]
        for r2 in res_ids[i + 1:]:
            l2 = resid_to_lipid.get(r2, "")
            if l1 == l2:
                continue
            mn2, mx2 = res_mins[r2], res_maxs[r2]
            if (
                mx1[0] + threshold < mn2[0] or mx2[0] + threshold < mn1[0]
                or mx1[1] + threshold < mn2[1] or mx2[1] + threshold < mn1[1]
                or mx1[2] + threshold < mn2[2] or mx2[2] + threshold < mn1[2]
            ):
                continue
            diff = res_arrays[r1][:, None, :] - res_arrays[r2][None, :, :]
            dists = np.sqrt((diff ** 2).sum(axis=-1))
            min_d = float(dists.min())
            if min_d < threshold:
                clash_pairs.append((r1, r2, l1, l2, min_d))

    if not clash_pairs:
        return []

    details = [
        f"  residue {r1} ({l1}) -- residue {r2} ({l2}): {d:.2f} A"
        for r1, r2, l1, l2, d in clash_pairs[:5]
    ]
    suffix = f" (showing first {min(5, len(clash_pairs))})" if len(clash_pairs) > 1 else ""
    summary = (
        f"{len(clash_pairs)} inter-species clash(es) detected "
        f"(threshold {threshold:.1f} A){suffix}. "
        "Run energy minimization before simulation."
    )
    return [summary] + details


def write_allatom_preview(
    layouts: dict[str, LeafletLayout],
    templates_dir: Path,
    output_path: Path,
    z_half_gap: float = _Z_TAIL,
    template_index: dict[str, Path] | None = None,
    seed: int = 42,
    clash_threshold: float = 2.0,
    tilt_angle: float = 0.0,
) -> tuple[int, list[str]]:
    """Tile lipid PDB templates across the leaflet grid.

    Each lipid is centered by its template XY centroid and given a random
    azimuthal rotation around the membrane normal (Z). The rotation seed is
    drawn from `seed` so builds are reproducible.

    Returns (n_atoms_written, warnings). warnings contains inter-species
    clash messages when atoms from different lipid types are closer than
    clash_threshold Angstroms.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    if template_index is None:
        template_index = {
            p.stem.upper(): p
            for p in sorted(templates_dir.glob("*.pdb"))
            if not p.name.startswith("._")
        }

    # cache: lipid_id -> (lines, z_tail, centroid_x, centroid_y)
    template_cache: dict[str, tuple[list[str], float, float, float]] = {}
    missing: set[str] = set()

    def _get_template(lipid_id: str) -> tuple[list[str], float, float, float] | None:
        key = lipid_id.upper()
        if key in template_cache:
            return template_cache[key]
        if key in template_index:
            lines = _load_template(template_index[key])
            z_tail = _template_z_tail(lines)
            cx, cy = _template_xy_centroid(lines)
            template_cache[key] = (lines, z_tail, cx, cy)
            return (lines, z_tail, cx, cy)
        missing.add(lipid_id)
        return None

    serial = 1
    resseq = 1
    all_lines: list[str] = []
    resid_to_lipid: dict[int, str] = {}

    for leaflet_name in ("upper", "lower"):
        if leaflet_name not in layouts:
            continue
        layout = layouts[leaflet_name]
        chain = _CHAIN[leaflet_name]
        z_flip = 1.0 if leaflet_name == "upper" else -1.0

        for pos in layout.positions:
            result = _get_template(pos.lipid_id)
            if result is None:
                continue
            tmpl, z_tail, cent_x, cent_y = result
            theta = rng.uniform(0.0, 2.0 * math.pi)
            tilt_phi = rng.uniform(0.0, 2.0 * math.pi) if tilt_angle != 0.0 else 0.0
            grid_x = pos.x * 10.0  # nm -> Angstrom
            grid_y = pos.y * 10.0

            placed = _place_atoms(
                tmpl, grid_x, grid_y, cent_x, cent_y,
                theta, z_flip, chain, resseq, z_tail, z_half_gap,
                tilt_angle_rad=math.radians(tilt_angle),
                tilt_phi=tilt_phi,
            )
            all_lines.extend(placed)
            resid_to_lipid[resseq] = pos.lipid_id.upper()
            resseq += 1

    # Compute box dimensions.
    box_x = max(lay.box_x() for lay in layouts.values()) * 10.0  # nm -> Angstrom
    box_y = max(lay.box_y() for lay in layouts.values()) * 10.0
    if all_lines:
        z_vals = [float(ln[46:54]) for ln in all_lines]
        box_z = (max(z_vals) - min(z_vals)) + 20.0
    else:
        box_z = 80.0

    warnings = _check_inter_species_clashes(all_lines, resid_to_lipid, clash_threshold)

    with output_path.open("w", encoding="utf-8") as fh:
        fh.write("REMARK Generated by BILBO (all-atom preview, visual inspection only).\n")
        fh.write("REMARK Not suitable for molecular dynamics simulation without further preparation.\n")
        if missing:
            fh.write(f"REMARK Missing templates (skipped): {', '.join(sorted(missing))}\n")
        if warnings:
            fh.write(f"REMARK {warnings[0]}\n")
        fh.write(
            f"CRYST1{box_x:9.3f}{box_y:9.3f}{box_z:9.3f}"
            f"  90.00  90.00  90.00 P 1           1\n"
        )
        for i, line in enumerate(all_lines):
            record = f"{line[:6]}{(serial + i) % 100000:5d}{line[11:]}\n"
            fh.write(record)
        fh.write("END\n")

    return len(all_lines), warnings
