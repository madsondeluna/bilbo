"""Export all-atom membrane preview by tiling lipid PDB templates."""

from pathlib import Path

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


def _place_atoms(
    atom_lines: list[str],
    dx: float,
    dy: float,
    z_flip: float,
    chain: str,
    resseq: int,
    z_tail: float,
    z_half_gap: float = _Z_TAIL,
) -> list[str]:
    """Translate x/y and place lipid relative to bilayer center.

    Normalizes z so the tail end (z_tail = template z_min) lands at
    +z_half_gap for the upper leaflet and -z_half_gap for the lower leaflet.
    This guarantees a 2*z_half_gap gap at the bilayer center regardless of
    the individual chain length, preventing atomic clashes between leaflets.
    Headgroups extend outward from the bilayer center in both leaflets.
    """
    out = []
    for line in atom_lines:
        x = float(line[30:38]) + dx
        y = float(line[38:46]) + dy
        z_norm = float(line[46:54]) - z_tail + z_half_gap
        z = z_flip * z_norm
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


def write_allatom_preview(
    layouts: dict[str, LeafletLayout],
    templates_dir: Path,
    output_path: Path,
    z_half_gap: float = _Z_TAIL,
    template_index: dict[str, Path] | None = None,
) -> int:
    """Tile lipid PDB templates across the leaflet grid.

    Each template is normalized so its headgroup (maximum z atom) is placed
    outward from z = 0 (bilayer center). Tails land at ±z_half_gap.

    Pass template_index to bypass the directory scan (used by membrane build).
    Returns total number of ATOM records written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if template_index is None:
        template_index = {
            p.stem.upper(): p
            for p in sorted(templates_dir.glob("*.pdb"))
            if not p.name.startswith("._")
        }
    template_cache: dict[str, tuple[list[str], float]] = {}
    missing: set[str] = set()

    def _get_template(lipid_id: str) -> tuple[list[str], float] | None:
        key = lipid_id.upper()
        if key in template_cache:
            return template_cache[key]
        if key in template_index:
            lines = _load_template(template_index[key])
            z_tail = _template_z_tail(lines)
            template_cache[key] = (lines, z_tail)
            return (lines, z_tail)
        missing.add(lipid_id)
        return None

    serial = 1
    resseq = 1
    all_lines: list[str] = []

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
            tmpl, z_tail = result
            # center x/y on the grid position (nm -> Angstrom)
            cx = pos.x * 10.0
            cy = pos.y * 10.0
            first = tmpl[0]
            tx0 = float(first[30:38])
            ty0 = float(first[38:46])
            dx = cx - tx0
            dy = cy - ty0

            placed = _place_atoms(tmpl, dx, dy, z_flip, chain, resseq, z_tail, z_half_gap)
            all_lines.extend(placed)
            resseq += 1

    # Compute box dimensions for CRYST1 record.
    # X/Y: take the maximum extent across all leaflets so that an asymmetric
    # build (different lipid counts per leaflet) is fully contained.
    # Z: actual atom extent plus 10 A buffer on each side.
    box_x = max(lay.box_x() for lay in layouts.values()) * 10.0  # nm -> Angstrom
    box_y = max(lay.box_y() for lay in layouts.values()) * 10.0
    if all_lines:
        z_vals = [float(ln[46:54]) for ln in all_lines]
        box_z = (max(z_vals) - min(z_vals)) + 20.0
    else:
        box_z = 80.0

    with output_path.open("w", encoding="utf-8") as fh:
        fh.write("REMARK Generated by BILBO (all-atom preview, visual inspection only).\n")
        fh.write("REMARK Not suitable for molecular dynamics simulation without further preparation.\n")
        if missing:
            fh.write(f"REMARK Missing templates (skipped): {', '.join(sorted(missing))}\n")
        fh.write(
            f"CRYST1{box_x:9.3f}{box_y:9.3f}{box_z:9.3f}"
            f"  90.00  90.00  90.00 P 1           1\n"
        )
        for i, line in enumerate(all_lines):
            record = f"{line[:6]}{serial + i:5d}{line[11:]}\n"
            fh.write(record)
        fh.write("END\n")

    return len(all_lines)
