"""BILBO web server — FastAPI backend."""

from __future__ import annotations

import hashlib
import math
import random as _random
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="BILBO web", docs_url=None, redoc_url=None)

_STATIC = Path(__file__).parent / "static"
_DATA_DIR = Path(__file__).parent.parent / "data" / "examples" / "charmm_gui"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/api/library")
async def library_list() -> JSONResponse:
    if not _DATA_DIR.is_dir():
        return JSONResponse([])
    names = sorted(p.stem for p in _DATA_DIR.glob("*.pdb") if not p.name.startswith("."))
    return JSONResponse(names)


@app.get("/api/library/{lipid_id}/pdb", response_class=PlainTextResponse)
async def library_pdb(lipid_id: str) -> PlainTextResponse:
    safe = Path(lipid_id.upper()).name
    pdb_path = _DATA_DIR / f"{safe}.pdb"
    if not pdb_path.is_file():
        raise HTTPException(status_code=404, detail=f"Lipid '{lipid_id}' not in library.")
    return PlainTextResponse(pdb_path.read_text(encoding="utf-8"))

# ── Ion definitions (CHARMM36 naming) ─────────────────────────────────────────
_ION_NAMES: dict[str, tuple[str, str]] = {
    "CA": ("CAL", "CA"),
    "NA": ("SOD", "NA"),
    "CL": ("CLA", "CL"),
    "MG": ("MG",  "MG"),
    "K":  ("POT", "K "),
    "ZN": ("ZN",  "ZN"),
    "PO4": ("PO4", "P "),
}

# Z separation (Å) between P atom and counter-ion along membrane normal.
# Approximates the Stern layer distance for Na+–phosphate coordination.
_ION_HEADGROUP_Z_SEP: float = 3.0

# Formal charges (e) for common CHARMM36 lipids
_LIPID_CHARGES: dict[str, int] = {
    "POPC": 0, "POPE": 0, "POPG": -1, "POPS": -1,
    "DPPC": 0, "DPPE": 0, "DPPG": -1, "DPPS": -1,
    "CHOL": 0, "CHL1": 0, "BSM": 0, "SM": 0, "SAPI": -1,
    "CL": -2, "CARD": -2, "PI": -1, "PA": -1, "PG": -1, "PS": -1,
}

_ANIONIC_RESNAMES: frozenset[str] = frozenset(
    name for name, chg in _LIPID_CHARGES.items() if chg < 0
)

# Bond length (Å), H-O-H half-angle (deg), has virtual M-site, M-site offset (Å)
_WATER_GEOM: dict[str, tuple[float, float, bool, float]] = {
    "tip3p": (0.9572, 52.26,  False, 0.0),
    "spc":   (1.0000, 54.735, False, 0.0),
    "spce":  (1.0000, 54.735, False, 0.0),
    "tip4p": (0.9572, 52.26,  True,  0.15),
}

_AVOGADRO = 6.02214076e23
_NM3_TO_L = 1e-24  # 1 nm³ = 1e-24 L

# Formal charges (e) at pH 7 for standard and CHARMM residue names
_RESIDUE_CHARGES: dict[str, int] = {
    "ASP": -1, "ASPP": 0,           # Asp deprotonated / protonated
    "GLU": -1, "GLUP": 0,           # Glu deprotonated / protonated
    "ARG": 1,
    "LYS": 1, "LSN": 0,             # Lys protonated / neutral
    "HIS": 0, "HIE": 0, "HID": 0,  # His neutral forms
    "HSD": 0, "HSE": 0,             # CHARMM neutral His
    "HIP": 1, "HSP": 1,             # His doubly protonated (+1)
}


def _calc_peptide_charge(atom_lines: list[str]) -> int:
    """Sum formal charges of all residues in a PDB atom list (at pH 7)."""
    seen: set[tuple[str, str]] = set()
    charge = 0
    for ln in atom_lines:
        chain = ln[21] if len(ln) > 21 else " "
        resseq = ln[22:26] if len(ln) > 26 else "   1"
        key = (chain, resseq.strip())
        if key in seen:
            continue
        seen.add(key)
        resname = ln[17:21].strip()
        charge += _RESIDUE_CHARGES.get(resname, 0)
    return charge


def _atom_lines(pdb_text: str) -> list[str]:
    return [ln for ln in pdb_text.splitlines() if ln.startswith(("ATOM", "HETATM"))]


def _centroid(lines: list[str]) -> tuple[float, float, float]:
    xs, ys, zs = [], [], []
    for ln in lines:
        try:
            xs.append(float(ln[30:38]))
            ys.append(float(ln[38:46]))
            zs.append(float(ln[46:54]))
        except (ValueError, IndexError):
            pass
    n = len(xs) or 1
    return sum(xs) / n, sum(ys) / n, sum(zs) / n


def _translate_replica(
    lines: list[str], dx: float, dy: float, dz: float,
    serial_start: int, chain: str,
) -> tuple[list[str], int]:
    """Translate one peptide replica, renumber serials, assign chain, reset resseq to 1."""
    out: list[str] = []
    old_res_to_new: dict[str, int] = {}
    cur_res = 1
    serial = serial_start
    for ln in lines:
        try:
            x = float(ln[30:38]) + dx
            y = float(ln[38:46]) + dy
            z = float(ln[46:54]) + dz
        except (ValueError, IndexError):
            continue
        old_res = ln[22:26]
        if old_res not in old_res_to_new:
            old_res_to_new[old_res] = cur_res
            cur_res += 1
        new_res = old_res_to_new[old_res]
        rec       = ln[:6]
        atom_name = ln[12:16]
        alt_loc   = ln[16] if len(ln) > 16 else " "
        res_name  = ln[17:21] if len(ln) > 21 else "LIP "
        tail      = ln[54:] if len(ln) > 54 else "  1.00  0.00"
        new_ln = (
            f"{rec}{serial % 100000:5d} {atom_name}{alt_loc}{res_name}{chain}{new_res % 10000:4d}"
            + (ln[26:30] if len(ln) > 30 else "    ")
            + f"{x:8.3f}{y:8.3f}{z:8.3f}"
            + tail
        )
        out.append(new_ln)
        serial += 1
    return out, serial


_PEP_CHAINS = [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c not in ("I", "L", "U", "W")]


def _parse_coord_list(s: str | None) -> list[float | None]:
    """Parse comma-separated coordinates, empty strings become None (auto)."""
    if not s or not s.strip():
        return []
    result: list[float | None] = []
    for part in s.split(","):
        part = part.strip()
        try:
            result.append(float(part) if part else None)
        except ValueError:
            result.append(None)
    return result


def _place_peptide_replicas(
    peptide_lines: list[str],
    n_replicas: int,
    surface: str,
    z_gap: float,
    z_max: float,
    z_min: float,
    box_x: float,
    box_y: float,
    serial_start: int,
    seed: int,
    fixed_xs: list[float | None] | None = None,
    fixed_ys: list[float | None] | None = None,
) -> list[str]:
    if not peptide_lines or n_replicas < 1:
        return []

    cx, cy, cz = _centroid(peptide_lines)
    rng = _random.Random(seed + 1000)
    out: list[str] = []
    serial = serial_start

    for i in range(n_replicas):
        chain = _PEP_CHAINS[i % len(_PEP_CHAINS)]

        x_spec = fixed_xs[i] if (fixed_xs and i < len(fixed_xs)) else None
        y_spec = fixed_ys[i] if (fixed_ys and i < len(fixed_ys)) else None

        tx = x_spec if x_spec is not None else (box_x / 2.0 if n_replicas == 1 else rng.uniform(0.0, box_x))
        ty = y_spec if y_spec is not None else (box_y / 2.0 if n_replicas == 1 else rng.uniform(0.0, box_y))

        if surface == "lower":
            tz = z_min - z_gap
        elif surface == "both":
            tz = z_max + z_gap if i % 2 == 0 else z_min - z_gap
        else:
            tz = z_max + z_gap

        placed, serial = _translate_replica(
            peptide_lines, tx - cx, ty - cy, tz - cz, serial, chain
        )
        out.extend(placed)

    return out


def _collect_anionic_sites(
    pdb_lines: list[str],
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """Return (upper_sites, lower_sites): P-atom XYZ for anionic lipid residues.

    Upper leaflet uses chain U; lower uses chain L.
    """
    upper: list[tuple[float, float, float]] = []
    lower: list[tuple[float, float, float]] = []
    for ln in pdb_lines:
        if not ln.startswith(("ATOM", "HETATM")):
            continue
        if ln[12:16].strip() != "P":
            continue
        resname = ln[17:21].strip().upper()
        if resname not in _ANIONIC_RESNAMES:
            continue
        chain = ln[21] if len(ln) > 21 else " "
        try:
            x, y, z = float(ln[30:38]), float(ln[38:46]), float(ln[46:54])
        except ValueError:
            continue
        if chain == "U":
            upper.append((x, y, z))
        elif chain == "L":
            lower.append((x, y, z))
    return upper, lower


def _make_ion_records(
    ion_type: str,
    sites_upper: list[tuple[float, float, float]],
    sites_lower: list[tuple[float, float, float]],
    surface: str,
    serial_start: int,
    seed: int,
) -> list[str]:
    """Place one counter-ion per anionic headgroup P atom.

    Ions are offset _ION_HEADGROUP_Z_SEP Å along the membrane normal (away
    from the bilayer center) so they sit in the Stern layer rather than
    overlapping the phosphate.
    """
    if ion_type not in _ION_NAMES:
        return []

    res_name, atom_name = _ION_NAMES[ion_type]
    rng = _random.Random(seed + 2000)

    if surface == "upper":
        sites = [(x, y, z + _ION_HEADGROUP_Z_SEP) for x, y, z in sites_upper]
    elif surface == "lower":
        sites = [(x, y, z - _ION_HEADGROUP_Z_SEP) for x, y, z in sites_lower]
    else:
        sites = (
            [(x, y, z + _ION_HEADGROUP_Z_SEP) for x, y, z in sites_upper]
            + [(x, y, z - _ION_HEADGROUP_Z_SEP) for x, y, z in sites_lower]
        )

    if not sites:
        return []

    rng.shuffle(sites)

    rname = res_name.ljust(3)[:3]
    aname = atom_name.ljust(2)
    out: list[str] = []
    serial = serial_start

    for resseq, (x, y, z) in enumerate(sites, start=1):
        out.append(
            f"HETATM{serial % 100000:5d}  {aname}  {rname} I{resseq % 10000:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00"
        )
        serial += 1

    return out


def _solvate(
    existing_lines: list[str],
    box_x: float,
    box_y: float,
    z_max: float,
    z_min: float,
    water_layer_a: float,
    water_model: str,
    seed: int,
    serial_start: int,
    ion_resseq_start: int,
    n_na: int,
    n_cl: int,
    grid_spacing: float = 3.1,
    clash_radius: float = 2.4,
) -> tuple[list[str], int, int, int]:
    """Place water (SOL, chain W) and bulk ions (SOD/CLA, chain I) around the membrane.

    Returns (pdb_lines, n_water_molecules, n_na_placed, n_cl_placed).
    """
    geom = _WATER_GEOM.get(water_model.lower(), _WATER_GEOM["tip3p"])
    bond_len, half_angle_deg, has_msite, msite_dist = geom
    half_angle = math.radians(half_angle_deg)
    hxy = bond_len * math.sin(half_angle)   # H lateral offset from O
    hzz = bond_len * math.cos(half_angle)   # H axial offset from O

    # Build occupied cell set from existing atom positions (3-D spatial hash)
    cell = clash_radius
    occupied: set[tuple[int, int, int]] = set()
    for ln in existing_lines:
        try:
            ax, ay, az = float(ln[30:38]), float(ln[38:46]), float(ln[46:54])
        except (ValueError, IndexError):
            continue
        bx, by, bz = int(ax / cell), int(ay / cell), int(az / cell)
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for dz in range(-1, 2):
                    occupied.add((bx + dx, by + dy, bz + dz))

    margin = 2.0  # Å gap between membrane surface and first water layer
    top_z0 = z_max + margin
    bot_z1 = z_min - margin

    rng = _random.Random(seed + 5000)
    nx = max(1, int(box_x / grid_spacing))
    ny = max(1, int(box_y / grid_spacing))
    nz = max(1, int(water_layer_a / grid_spacing))

    valid: list[tuple[float, float, float, int]] = []  # (x, y, z, slab_dir)
    for slab_dir, z0 in ((1, top_z0), (-1, bot_z1)):
        for k in range(nz):
            zk = z0 + slab_dir * k * grid_spacing
            for j in range(ny):
                y = j * grid_spacing + rng.uniform(0.0, grid_spacing * 0.25)
                for i in range(nx):
                    x = i * grid_spacing + rng.uniform(0.0, grid_spacing * 0.25)
                    bx, by, bz = int(x / cell), int(y / cell), int(zk / cell)
                    if (bx, by, bz) in occupied:
                        continue
                    valid.append((x, y, zk, slab_dir))
                    occupied.add((bx, by, bz))

    rng.shuffle(valid)

    n_na_placed = min(n_na, len(valid))
    n_cl_placed = min(n_cl, max(0, len(valid) - n_na_placed))
    n_water = len(valid) - n_na_placed - n_cl_placed

    out: list[str] = []
    serial = serial_start
    ion_res = ion_resseq_start

    for x, y, z, _ in valid[:n_na_placed]:
        out.append(
            f"HETATM{serial % 100000:5d}  NA  SOD I{ion_res % 10000:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00"
        )
        serial += 1
        ion_res += 1

    for x, y, z, _ in valid[n_na_placed:n_na_placed + n_cl_placed]:
        out.append(
            f"HETATM{serial % 100000:5d}  CL  CLA I{ion_res % 10000:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00"
        )
        serial += 1
        ion_res += 1

    water_res = 1
    for x, y, z, slab_dir in valid[n_na_placed + n_cl_placed:]:
        theta = rng.uniform(0.0, 2.0 * math.pi)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        h1x, h1y = x + hxy * cos_t, y + hxy * sin_t
        h2x, h2y = x - hxy * cos_t, y - hxy * sin_t
        hz = z - slab_dir * hzz  # H atoms point toward membrane

        wr = water_res % 10000
        out.append(
            f"ATOM  {serial % 100000:5d}  OW  SOL W{wr:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00"
        )
        serial += 1
        out.append(
            f"ATOM  {serial % 100000:5d}  HW1 SOL W{wr:4d}    "
            f"{h1x:8.3f}{h1y:8.3f}{hz:8.3f}  1.00  0.00"
        )
        serial += 1
        out.append(
            f"ATOM  {serial % 100000:5d}  HW2 SOL W{wr:4d}    "
            f"{h2x:8.3f}{h2y:8.3f}{hz:8.3f}  1.00  0.00"
        )
        serial += 1
        if has_msite:
            mz = z - slab_dir * msite_dist
            out.append(
                f"ATOM  {serial % 100000:5d}  MW  SOL W{wr:4d}    "
                f"{x:8.3f}{y:8.3f}{mz:8.3f}  1.00  0.00"
            )
            serial += 1
        water_res += 1

    return out, n_water, n_na_placed, n_cl_placed


@app.post("/api/peptide_charge")
async def peptide_charge_endpoint(pdb_file: UploadFile = File(...)) -> JSONResponse:
    raw = (await pdb_file.read()).decode("utf-8", errors="replace")
    charge = _calc_peptide_charge(_atom_lines(raw))
    return JSONResponse({"charge": charge})


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}



@app.post("/api/build")
async def build_membrane(
    upper_files: list[UploadFile] = File(...),
    upper_counts: str = Form(...),
    symmetric: str = Form("true"),
    lower_files: Optional[list[UploadFile]] = File(None),
    lower_counts: Optional[str] = Form(None),
    seed: int = Form(42),
    spacing: Optional[str] = Form(None),
    box_side: Optional[str] = Form(None),
    bilayer_gap: float = Form(6.0),
    sorting: str = Form("random"),
    tilt_angle: float = Form(0.0),
    # Surface peptide
    peptide_file: Optional[UploadFile] = File(None),
    peptide_replicas: int = Form(1),
    peptide_surface: str = Form("upper"),
    peptide_z_gap: float = Form(5.0),
    peptide_x: Optional[str] = Form(None),
    peptide_y: Optional[str] = Form(None),
    # Coordination ions
    ion_type: Optional[str] = Form(None),
    ion_count: int = Form(0),
    ion_surface: str = Form("both"),
    ion_z_offset: float = Form(0.0),
    # Solvation
    solvate: Optional[str] = Form(None),
    water_model: str = Form("tip3p"),
    box_z_nm_input: Optional[float] = Form(None),
    sol_ion_conc_mM: float = Form(150.0),
    peptide_charge: int = Form(0),
) -> JSONResponse:
    from bilbo.builders.apl_check import weighted_spacing as calc_spacing
    from bilbo.builders.composition_expander import ExpandedComposition
    from bilbo.builders.leaflet_layout import build_leaflet_layout
    from bilbo.exporters.allatom_preview import write_allatom_preview
    from bilbo.exporters.gro_exporter import pdb_to_gro
    from bilbo.exporters.gromacs_topology import write_gromacs_topology

    is_symmetric = symmetric.lower() in ("true", "1", "yes")

    upper_cnt_list = [int(c.strip()) for c in upper_counts.split(",") if c.strip()]
    if len(upper_cnt_list) != len(upper_files):
        raise HTTPException(
            status_code=400,
            detail=f"upper_counts has {len(upper_cnt_list)} values but {len(upper_files)} files were uploaded.",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        tmpl_dir = tmp / "templates"
        tmpl_dir.mkdir()
        out_dir = tmp / "output"
        out_dir.mkdir()

        upper_specs: dict[str, tuple[Path, int]] = {}
        for uf, cnt in zip(upper_files, upper_cnt_list):
            stem = Path(uf.filename or "LIP").stem.upper()
            dest = tmpl_dir / f"{stem}.pdb"
            dest.write_bytes(await uf.read())
            upper_specs[stem] = (dest, cnt)

        if is_symmetric:
            lower_specs = dict(upper_specs)
        else:
            lower_cnt_list = [int(c.strip()) for c in (lower_counts or "").split(",") if c.strip()]
            lower_file_list = lower_files or []
            if len(lower_cnt_list) != len(lower_file_list):
                raise HTTPException(
                    status_code=400,
                    detail="lower_counts length must match number of lower PDB files.",
                )
            lower_specs = {}
            for lf, cnt in zip(lower_file_list, lower_cnt_list):
                stem = Path(lf.filename or "LIP").stem.upper()
                dest = tmpl_dir / f"{stem}.pdb"
                dest.write_bytes(await lf.read())
                lower_specs[stem] = (dest, cnt)

        template_index: dict[str, Path] = {}
        for lid, (p, _) in upper_specs.items():
            template_index[lid] = p
        for lid, (p, _) in lower_specs.items():
            template_index[lid] = p

        upper_counts_dict = {lid: cnt for lid, (_, cnt) in upper_specs.items()}
        lower_counts_dict = {lid: cnt for lid, (_, cnt) in lower_specs.items()}
        counts_by_leaflet = {"upper": upper_counts_dict, "lower": lower_counts_dict}

        resolved_spacing: float
        warnings: list[str] = []

        # box_side (nm) overrides spacing — derive spacing from desired box size
        if box_side and box_side.strip():
            try:
                bs = float(box_side)
            except ValueError:
                raise HTTPException(status_code=400, detail="box_side must be a number.")
            n_max = max(
                sum(upper_counts_dict.values()),
                sum(lower_counts_dict.values()) if lower_counts_dict else 1,
            )
            nx_max = math.ceil(math.sqrt(n_max))
            resolved_spacing = bs / nx_max
        elif spacing and spacing.strip():
            try:
                resolved_spacing = float(spacing)
            except ValueError:
                raise HTTPException(status_code=400, detail="spacing must be a number.")
        else:
            ws = calc_spacing(counts_by_leaflet)
            if ws is None:
                warnings.append("APL reference missing for one or more species; using default spacing 0.7 nm.")
                resolved_spacing = 0.7
            else:
                resolved_spacing = ws

        apl_a2 = (resolved_spacing * 10.0) ** 2
        if apl_a2 < 35.0:
            warnings.append(
                f"Spacing {resolved_spacing:.3f} nm gives APL {apl_a2:.1f} A² "
                "(below physiological minimum ~35 A² for phospholipids)."
            )
        elif apl_a2 > 80.0:
            warnings.append(
                f"Spacing {resolved_spacing:.3f} nm gives APL {apl_a2:.1f} A² "
                "(above physiological maximum ~80 A² for phospholipids)."
            )

        expanded = [
            ExpandedComposition(leaflet="upper", counts=upper_counts_dict, rounding_errors={}),
            ExpandedComposition(leaflet="lower", counts=lower_counts_dict, rounding_errors={}),
        ]

        try:
            layouts = build_leaflet_layout(expanded, sorting, seed, spacing=resolved_spacing)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Layout error: {exc}")

        aa_out = out_dir / "preview_allatom.pdb"
        try:
            n_lipid_atoms, clash_warns = write_allatom_preview(
                layouts,
                tmpl_dir,
                aa_out,
                z_half_gap=bilayer_gap / 2.0,
                template_index=template_index,
                seed=seed,
                tilt_angle=tilt_angle,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Preview error: {exc}")

        warnings.extend(clash_warns)

        top_out = out_dir / "topol.top"
        try:
            write_gromacs_topology(layouts, top_out)
            topology = top_out.read_text(encoding="utf-8")
        except Exception:
            topology = ""

        membrane_pdb = aa_out.read_text(encoding="utf-8") if aa_out.exists() else ""

        # Box dimensions (Angstrom)
        box_x = max(lay.box_x() for lay in layouts.values()) * 10.0
        box_y = max(lay.box_y() for lay in layouts.values()) * 10.0

        # Membrane z extent from actual atom coords
        mem_z_vals = [float(ln[46:54]) for ln in membrane_pdb.splitlines()
                      if ln.startswith(("ATOM", "HETATM"))]
        z_max = max(mem_z_vals) if mem_z_vals else bilayer_gap / 2.0 + 20.0
        z_min = min(mem_z_vals) if mem_z_vals else -(bilayer_gap / 2.0 + 20.0)

        # Current serial = n_lipid_atoms + 1 (membrane serials are 1..n_lipid_atoms)
        next_serial = n_lipid_atoms + 1

        # Surface peptide replicas
        peptide_lines_placed: list[str] = []
        if peptide_file:
            raw = (await peptide_file.read()).decode("utf-8", errors="replace")
            pep_lines = _atom_lines(raw)
            if pep_lines:
                fxs = _parse_coord_list(peptide_x)
                fys = _parse_coord_list(peptide_y)
                peptide_lines_placed = _place_peptide_replicas(
                    pep_lines, peptide_replicas, peptide_surface,
                    peptide_z_gap, z_max, z_min, box_x, box_y,
                    next_serial, seed,
                    fixed_xs=fxs or None,
                    fixed_ys=fys or None,
                )
                next_serial += len(peptide_lines_placed)

        # Coordination ions: target the phosphate Z level of each leaflet.
        # Extract mean Z of chain-U and chain-L P atoms; fall back to z_max/z_min.
        ion_lines: list[str] = []
        if ion_type and ion_type.strip() and ion_count > 0:
            pdb_atom_lines = [ln for ln in membrane_pdb.splitlines()
                              if ln.startswith(("ATOM", "HETATM"))]
            sites_upper, sites_lower = _collect_anionic_sites(pdb_atom_lines)
            ion_lines = _make_ion_records(
                ion_type.strip().upper(),
                sites_upper, sites_lower,
                ion_surface, next_serial, seed,
            )
            next_serial += len(ion_lines)

        # Solvation: water + bulk ions
        solvate_enabled = bool(solvate and solvate.strip().lower() in ("true", "1", "yes"))
        solv_lines: list[str] = []
        n_water = 0
        n_sol_na = 0
        n_sol_cl = 0
        system_charge = 0
        charge_after = 0
        n_na_neutral = 0
        n_cl_neutral = 0
        n_pairs = 0
        water_layer_a = 30.0  # default 3 nm per side

        if solvate_enabled:
            # Compute water layer thickness from total box Z if provided
            if box_z_nm_input is not None and box_z_nm_input > 0:
                mem_thickness = z_max - z_min  # Angstroms
                requested_layer = (box_z_nm_input * 10.0 - mem_thickness - 4.0) / 2.0
                if requested_layer < 10.0:
                    actual_box_z = round((mem_thickness + 4.0 + 2.0 * 10.0) / 10.0, 2)
                    warnings.append(
                        f"Box Z {box_z_nm_input} nm is too small for this membrane "
                        f"({round(mem_thickness/10, 2)} nm thick). "
                        f"Using {actual_box_z} nm instead (minimum 1 nm water each side)."
                    )
                water_layer_a = max(10.0, requested_layer)
            # else: water_layer_a stays at default 30.0 (3 nm/side)

            lipid_chg = sum(_LIPID_CHARGES.get(lid, 0) * cnt for lid, cnt in upper_counts_dict.items())
            lipid_chg += sum(_LIPID_CHARGES.get(lid, 0) * cnt for lid, cnt in lower_counts_dict.items())
            system_charge = lipid_chg + peptide_charge  # charge BEFORE any solvation ions

            n_na_neutral = max(0, -system_charge)  # Na+ needed to neutralize
            n_cl_neutral = max(0, system_charge)   # Cl- needed to neutralize

            water_vol_nm3 = (box_x / 10.0) * (box_y / 10.0) * (2.0 * water_layer_a / 10.0)
            n_pairs = round((sol_ion_conc_mM / 1000.0) * water_vol_nm3 * _NM3_TO_L * _AVOGADRO)
            n_pairs = max(0, n_pairs)

            current_atom_lines = (
                [ln for ln in membrane_pdb.splitlines() if ln.startswith(("ATOM", "HETATM"))]
                + peptide_lines_placed
                + ion_lines
            )
            ion_resseq_start = ion_count + 1  # continue after coordination ions

            solv_lines, n_water, n_sol_na, n_sol_cl = _solvate(
                current_atom_lines, box_x, box_y, z_max, z_min,
                water_layer_a, water_model, seed, next_serial,
                ion_resseq_start,
                n_na=n_na_neutral + n_pairs,
                n_cl=n_cl_neutral + n_pairs,
            )
            charge_after = system_charge + n_sol_na - n_sol_cl

        # Assemble final PDB: header + membrane + peptides + coord-ions + solv + END
        final_lines: list[str] = []
        for ln in membrane_pdb.splitlines():
            if ln.startswith("END"):
                continue
            final_lines.append(ln)
        final_lines.extend(peptide_lines_placed)
        final_lines.extend(ion_lines)
        final_lines.extend(solv_lines)
        final_lines.append("END")
        final_pdb = "\n".join(final_lines) + "\n"

        n_total_atoms = n_lipid_atoms + len(peptide_lines_placed) + len(ion_lines) + len(solv_lines)

        # Compute peptide centroid per replica for reporting
        pep_centroids: list[dict] = []
        if peptide_lines_placed:
            # Group by chain to get per-replica centroids
            from collections import defaultdict
            chain_coords: dict[str, list] = defaultdict(list)
            for ln in peptide_lines_placed:
                if ln.startswith(("ATOM", "HETATM")):
                    ch = ln[21]
                    try:
                        chain_coords[ch].append((float(ln[30:38]), float(ln[38:46]), float(ln[46:54])))
                    except (ValueError, IndexError):
                        pass
            for ch, coords in sorted(chain_coords.items()):
                xs_ = [c[0] for c in coords]
                ys_ = [c[1] for c in coords]
                zs_ = [c[2] for c in coords]
                pep_centroids.append({
                    "chain": ch,
                    "x": round(sum(xs_) / len(xs_), 2),
                    "y": round(sum(ys_) / len(ys_), 2),
                    "z": round(sum(zs_) / len(zs_), 2),
                })

        # Topology: append solvent/ion molecule counts if solvated
        if solvate_enabled and topology:
            wm_itp = {"tip3p": "tip3p", "spc": "spc", "spce": "spce", "tip4p": "tip4p"}.get(
                water_model.lower(), "tip3p"
            )
            topology += f'\n#include "charmm36.ff/{wm_itp}.itp"\n'
            topology += '#include "charmm36.ff/ions.itp"\n'
            if n_water > 0:
                topology += f"\nSOL              {n_water}\n"
            if n_sol_na > 0:
                topology += f"SOD              {n_sol_na}\n"
            if n_sol_cl > 0:
                topology += f"CLA              {n_sol_cl}\n"

        box_z_nm = round((z_max - z_min) / 10.0, 3)
        if solvate_enabled:
            box_z_nm = round((z_max - z_min + 2.0 * (2.0 + water_layer_a)) / 10.0, 3)

        # Leaflet scatter plot — PNG encoded as base64
        leaflet_plot_b64 = ""
        try:
            from base64 import b64encode
            from bilbo.exporters.leaflet_png import write_leaflet_png

            plot_tmp = tmp / "leaflet_plot.png"
            pep_plot: list[dict] = []
            if pep_centroids:
                for i, c in enumerate(pep_centroids):
                    if peptide_surface == "both":
                        leaflet = "upper" if i % 2 == 0 else "lower"
                    else:
                        leaflet = peptide_surface
                    pep_plot.append({
                        "peptide_id": c["chain"],
                        "leaflet": leaflet,
                        "translation_vector": [c["x"], c["y"], c["z"]],
                    })
            write_leaflet_png(layouts, plot_tmp, peptide_placements=pep_plot or None)
            if plot_tmp.exists():
                leaflet_plot_b64 = b64encode(plot_tmp.read_bytes()).decode()
        except Exception:
            pass

        return JSONResponse({
            "pdb": final_pdb,
            "gro": pdb_to_gro(final_pdb),
            "n_atoms": n_total_atoms,
            "n_lipid_atoms": n_lipid_atoms,
            "n_peptide_atoms": len(peptide_lines_placed),
            "n_ions": len(ion_lines),
            "n_water": n_water,
            "n_sol_na": n_sol_na,
            "n_sol_cl": n_sol_cl,
            "charge_before": system_charge,
            "charge_after": charge_after,
            "n_na_neutral": n_na_neutral,
            "n_cl_neutral": n_cl_neutral,
            "n_pairs": n_pairs,
            "sol_ion_conc_mM": sol_ion_conc_mM if solvate_enabled else None,
            "water_model": water_model if solvate_enabled else None,
            "n_lipids": {
                "upper": sum(upper_counts_dict.values()),
                "lower": sum(lower_counts_dict.values()),
            },
            "spacing_nm": round(resolved_spacing, 4),
            "apl_a2": round(apl_a2, 2),
            "box_x_nm": round(box_x / 10.0, 3),
            "box_y_nm": round(box_y / 10.0, 3),
            "box_z_nm": box_z_nm,
            "pep_centroids": pep_centroids,
            "warnings": warnings,
            "topology": topology,
            "composition": {
                "upper": upper_counts_dict,
                "lower": lower_counts_dict,
            },
            "leaflet_plot_b64": leaflet_plot_b64,
        })
