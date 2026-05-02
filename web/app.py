"""BILBO web server — FastAPI backend."""

from __future__ import annotations

import hashlib
import random as _random
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="BILBO web", docs_url=None, redoc_url=None)

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# ── Ion definitions (CHARMM36 naming) ─────────────────────────────────────────
_ION_NAMES: dict[str, tuple[str, str]] = {
    "CA": ("CAL", "CA"),
    "NA": ("SOD", "NA"),
    "CL": ("CLA", "CL"),
    "MG": ("MG",  "MG"),
    "K":  ("POT", "K "),
    "ZN": ("ZN",  "ZN"),
}


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
            f"{rec}{serial:5d} {atom_name}{alt_loc}{res_name}{chain}{new_res:4d}"
            + (ln[26:30] if len(ln) > 30 else "    ")
            + f"{x:8.3f}{y:8.3f}{z:8.3f}"
            + tail
        )
        out.append(new_ln)
        serial += 1
    return out, serial


_PEP_CHAINS = [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c not in ("I", "L", "U")]


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
) -> list[str]:
    if not peptide_lines or n_replicas < 1:
        return []

    cx, cy, cz = _centroid(peptide_lines)
    rng = _random.Random(seed + 1000)
    out: list[str] = []
    serial = serial_start

    for i in range(n_replicas):
        chain = _PEP_CHAINS[i % len(_PEP_CHAINS)]
        tx = rng.uniform(0.0, box_x)
        ty = rng.uniform(0.0, box_y)
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


def _make_ion_records(
    ion_type: str,
    count: int,
    surface: str,
    z_offset: float,
    z_half_gap: float,
    box_x: float,
    box_y: float,
    serial_start: int,
    seed: int,
) -> list[str]:
    if ion_type not in _ION_NAMES or count < 1:
        return []

    res_name, atom_name = _ION_NAMES[ion_type]
    rng = _random.Random(seed + 2000)
    out: list[str] = []
    serial = serial_start
    resseq = 1

    rname = res_name.ljust(3)[:3]
    aname = atom_name.ljust(2)

    for i in range(count):
        x = rng.uniform(0.0, box_x)
        y = rng.uniform(0.0, box_y)
        if surface == "upper":
            z = z_half_gap + z_offset
        elif surface == "lower":
            z = -(z_half_gap + z_offset)
        else:
            z = z_half_gap + z_offset if i % 2 == 0 else -(z_half_gap + z_offset)

        ln = (
            f"HETATM{serial:5d}  {aname}  {rname} I{resseq:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00"
        )
        out.append(ln)
        serial += 1
        resseq += 1

    return out


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
    bilayer_gap: float = Form(6.0),
    sorting: str = Form("random"),
    # Surface peptide
    peptide_file: Optional[UploadFile] = File(None),
    peptide_replicas: int = Form(1),
    peptide_surface: str = Form("upper"),
    peptide_z_gap: float = Form(5.0),
    # Coordination ions
    ion_type: Optional[str] = Form(None),
    ion_count: int = Form(0),
    ion_surface: str = Form("both"),
    ion_z_offset: float = Form(0.0),
) -> JSONResponse:
    from bilbo.builders.apl_check import weighted_spacing as calc_spacing
    from bilbo.builders.composition_expander import ExpandedComposition
    from bilbo.builders.leaflet_layout import build_leaflet_layout
    from bilbo.exporters.allatom_preview import write_allatom_preview
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
        if spacing and spacing.strip():
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
                peptide_lines_placed = _place_peptide_replicas(
                    pep_lines, peptide_replicas, peptide_surface,
                    peptide_z_gap, z_max, z_min, box_x, box_y,
                    next_serial, seed,
                )
                next_serial += len(peptide_lines_placed)

        # Coordination ions
        ion_lines: list[str] = []
        if ion_type and ion_type.strip() and ion_count > 0:
            ion_lines = _make_ion_records(
                ion_type.strip().upper(), ion_count,
                ion_surface, ion_z_offset, bilayer_gap / 2.0,
                box_x, box_y, next_serial, seed,
            )

        # Assemble final PDB: header + membrane + peptides + ions + END
        final_lines: list[str] = []
        for ln in membrane_pdb.splitlines():
            if ln.startswith("END"):
                continue
            final_lines.append(ln)
        final_lines.extend(peptide_lines_placed)
        final_lines.extend(ion_lines)
        final_lines.append("END")
        final_pdb = "\n".join(final_lines) + "\n"

        n_total_atoms = n_lipid_atoms + len(peptide_lines_placed) + len(ion_lines)

        return JSONResponse({
            "pdb": final_pdb,
            "n_atoms": n_total_atoms,
            "n_lipid_atoms": n_lipid_atoms,
            "n_peptide_atoms": len(peptide_lines_placed),
            "n_ions": len(ion_lines),
            "n_lipids": {
                "upper": sum(upper_counts_dict.values()),
                "lower": sum(lower_counts_dict.values()),
            },
            "spacing_nm": round(resolved_spacing, 4),
            "apl_a2": round(apl_a2, 2),
            "warnings": warnings,
            "topology": topology,
        })
