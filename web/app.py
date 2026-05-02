"""BILBO web server — FastAPI backend."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="BILBO web", docs_url=None, redoc_url=None)

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


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
    protein_file: Optional[UploadFile] = File(None),
    seed: int = Form(42),
    spacing: Optional[str] = Form(None),
    bilayer_gap: float = Form(6.0),
    sorting: str = Form("random"),
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

        # Save uploaded PDB files
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
            n_atoms, clash_warns = write_allatom_preview(
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

        pdb_content = aa_out.read_text(encoding="utf-8") if aa_out.exists() else ""

        if protein_file:
            protein_pdb = (await protein_file.read()).decode("utf-8", errors="replace")
        else:
            protein_pdb = ""

        return JSONResponse({
            "pdb": pdb_content,
            "protein_pdb": protein_pdb,
            "n_atoms": n_atoms,
            "n_lipids": {
                "upper": sum(upper_counts_dict.values()),
                "lower": sum(lower_counts_dict.values()),
            },
            "spacing_nm": round(resolved_spacing, 4),
            "apl_a2": round(apl_a2, 2),
            "warnings": warnings,
            "topology": topology,
        })
