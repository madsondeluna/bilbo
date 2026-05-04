"""BILBO web server — FastAPI backend."""

from __future__ import annotations

import base64
import gzip
import hashlib
import html as _html_lib
import io
import json
import math
import os
import random as _random
import re as _re
from sqlalchemy import create_engine, text, pool as sa_pool
import tempfile
import threading
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="BILBO web", docs_url=None, redoc_url=None)

# ── Email infrastructure (Resend) ─────────────────────────────────────────────
ISSUES_URL = 'https://github.com/madsondeluna/bilbo/issues'

EMAIL_SIGNATURE = (
    '\n'
    'BILBO Team\n'
    'Principal Developer: madsondeluna@gmail.com\n'
    'Repository: https://github.com/madsondeluna/bilbo\n'
)

EMAIL_CLOSING = {
    'en': 'Kind regards,\n',
    'fr': 'Cordialement,\n',
    'es': 'Saludos cordiales,\n',
    'pt': 'Atenciosamente,\n',
    'zh': '此致敬礼，\n',
}

EMAIL_FOOTER = {
    'en': (
        '\n'
        'This is an automated message, you do not need to reply.\n'
        'Your data is transmitted with end-to-end TLS encryption.\n'
    ),
    'fr': (
        '\n'
        'Ceci est un message automatique, vous n\'avez pas besoin de répondre.\n'
        'Vos données sont transmises avec chiffrement TLS de bout en bout.\n'
    ),
    'es': (
        '\n'
        'Este es un mensaje automático, no es necesario responder.\n'
        'Tus datos se transmiten con cifrado TLS de extremo a extremo.\n'
    ),
    'pt': (
        '\n'
        'Esta é uma mensagem automática, você não precisa responder.\n'
        'Seus dados são transmitidos com criptografia TLS de ponta a ponta.\n'
    ),
    'zh': (
        '\n'
        '这是一封自动邮件，您无需回复。\n'
        '您的数据通过端到端 TLS 加密传输。\n'
    ),
}


def _wrap_email_html(text_body: str) -> str:
    """Wrap plain text email in HTML with sans-serif left-aligned style.
    Tokens wrapped in **...** become <strong>."""
    escaped = _html_lib.escape(text_body)
    escaped = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    html_body = escaped.replace('\n', '<br>')
    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#ffffff;">'
        '<div style="max-width:680px;margin:0;padding:20px;background:#ffffff;text-align:left;'
        'font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#222222;">'
        f'{html_body}'
        '</div></body></html>'
    )


# Threshold above which output files are bundled into a single ZIP archive
# before being attached. Resend allows ~40 MB per request, but base64 inflates
# raw bytes by ~33% and downstream providers (Gmail) reject above ~25 MB.
EMAIL_ZIP_THRESHOLD_BYTES = 2 * 1024 * 1024


def _pack_attachments(files: list[tuple[str, bytes]]) -> tuple[list[dict], list[str] | None]:
    """Build Resend-style attachments. If total raw size exceeds the threshold,
    bundle all files into a single ZIP and return its contents list as the
    second tuple element. Otherwise return individual attachments and None."""
    total = sum(len(b) for _, b in files)
    if total <= EMAIL_ZIP_THRESHOLD_BYTES or len(files) <= 1:
        return (
            [
                {'filename': name, 'content': base64.b64encode(data).decode('ascii')}
                for name, data in files
            ],
            None,
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, data in files:
            zf.writestr(name, data)
    zip_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return (
        [{'filename': 'bilbo_results.zip', 'content': zip_b64}],
        [name for name, _ in files],
    )


def _resend_send(payload: dict) -> tuple[bool, str]:
    """POST email payload to Resend API. Returns (ok, message_or_error)."""
    api_key = os.environ.get('RESEND_API_KEY', '')
    if not api_key:
        return False, 'Email service not configured.'
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.resend.com/emails',
        data=data,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'BILBO/0.1.0 (https://github.com/madsondeluna/bilbo)',
            'Accept': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req) as resp:
            resp.read()
        return True, 'ok'
    except urllib.error.HTTPError as e:
        raw = ''
        try:
            raw = e.read().decode('utf-8', errors='replace')
        except Exception:
            pass
        msg = raw
        try:
            d = json.loads(raw) if raw else {}
            msg = d.get('message') or d.get('error') or raw
        except Exception:
            pass
        return False, f'Resend {e.code}: {msg}'
    except Exception as e:
        return False, str(e)


_STATIC = Path(__file__).parent / "static"
_DATA_DIR = Path(__file__).parent.parent / "data" / "examples" / "charmm_gui"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


# ── Usage stats ────────────────────────────────────────────────────────────────

def _send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    def _post() -> None:
        try:
            payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()


_db_lock = threading.Lock()
_engine = None


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    url = os.environ.get("DATABASE_URL", "")
    if url:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        _engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2)
    else:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.db")
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            poolclass=sa_pool.StaticPool,
        )
    return _engine


def _is_pg() -> bool:
    return _get_engine().dialect.name == "postgresql"


def _init_stats_db() -> None:
    with _db_lock:
        with _get_engine().begin() as conn:
            if _is_pg():
                conn.execute(text("CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value BIGINT DEFAULT 0)"))
                conn.execute(text("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY)"))
                for k in ("total_builds", "total_atoms", "unique_sessions"):
                    conn.execute(text("INSERT INTO stats (key, value) VALUES (:k, 0) ON CONFLICT DO NOTHING"), {"k": k})
            else:
                conn.execute(text("CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER DEFAULT 0)"))
                conn.execute(text("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY)"))
                for k in ("total_builds", "total_atoms", "unique_sessions"):
                    conn.execute(text("INSERT OR IGNORE INTO stats VALUES (:k, 0)"), {"k": k})


def _register_session(session_id: str) -> None:
    with _db_lock:
        with _get_engine().begin() as conn:
            if _is_pg():
                result = conn.execute(
                    text("INSERT INTO sessions (id) VALUES (:id) ON CONFLICT DO NOTHING"),
                    {"id": session_id},
                )
                if result.rowcount:
                    conn.execute(text("UPDATE stats SET value = value + 1 WHERE key = 'unique_sessions'"))
            else:
                exists = conn.execute(text("SELECT 1 FROM sessions WHERE id = :id"), {"id": session_id}).fetchone()
                if not exists:
                    conn.execute(text("INSERT OR IGNORE INTO sessions VALUES (:id)"), {"id": session_id})
                    conn.execute(text("UPDATE stats SET value = value + 1 WHERE key = 'unique_sessions'"))


def _increment_stats(atom_count: int) -> None:
    with _db_lock:
        with _get_engine().begin() as conn:
            conn.execute(text("UPDATE stats SET value = value + 1 WHERE key = 'total_builds'"))
            conn.execute(text("UPDATE stats SET value = value + :n WHERE key = 'total_atoms'"), {"n": atom_count})


def _get_stats() -> dict:
    with _db_lock:
        with _get_engine().connect() as conn:
            rows = conn.execute(text("SELECT key, value FROM stats")).fetchall()
            return {k: v for k, v in rows}


_init_stats_db()

_ADMIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BILBO stats</title>
<style>
  body { font-family: monospace; background: #0f0f0f; color: #e0e0e0; padding: 40px; }
  h1 { font-size: 1.1rem; color: #aaa; margin-bottom: 28px; letter-spacing: 0.08em; }
  .grid { display: flex; gap: 16px; flex-wrap: wrap; }
  .card { background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 6px;
          padding: 20px 28px; min-width: 150px; text-align: center; }
  .num { font-size: 2.4rem; color: #fff; }
  .lbl { font-size: 0.72rem; color: #666; margin-top: 6px; letter-spacing: 0.05em; }
  a { color: #555; font-size: 0.78rem; text-decoration: none; }
  a:hover { color: #aaa; }
</style>
</head>
<body>
<h1>BILBO / usage stats</h1>
<div class="grid" id="cards">loading...</div>
<p style="margin-top:32px"><a href="/">back to app</a></p>
<script>
fetch('/stats').then(r=>r.json()).then(d=>{
  const labels = {total_builds:'builds',total_lipids:'lipids placed',unique_sessions:'unique sessions'};
  document.getElementById('cards').innerHTML = Object.entries(labels).map(
    ([k,l]) => '<div class="card"><div class="num">'+(d[k]||0)+'</div><div class="lbl">'+l+'</div></div>'
  ).join('');
});
</script>
</body>
</html>"""


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
async def root(request: Request) -> HTMLResponse:
    resp = HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))
    sid = request.cookies.get("_bilbo_sid")
    if not sid:
        sid = str(uuid.uuid4())
        resp.set_cookie("_bilbo_sid", sid, max_age=365 * 24 * 3600, samesite="lax", httponly=True)
    try:
        _register_session(sid)
    except Exception:
        pass
    return resp


@app.get("/stats")
async def stats_endpoint() -> JSONResponse:
    return JSONResponse(_get_stats())


@app.get("/admin", response_class=HTMLResponse)
async def admin() -> HTMLResponse:
    return HTMLResponse(_ADMIN_PAGE)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def _format_composition(comp_dict: dict) -> str:
    """Build a multiline string of lipid: count entries."""
    if not comp_dict:
        return '(none)'
    return '\n'.join(f'  {name}: **{count}**' for name, count in comp_dict.items())


def _build_summary_lines(summary: dict, lang: str) -> str:
    """Build the localized 'Build summary' block from build data."""
    labels = {
        'en': {
            'box': 'Box (X×Y×Z, nm)',
            'spacing': 'Spacing (nm)',
            'apl': 'Area per lipid (Å²)',
            'upper': 'Upper leaflet',
            'lower': 'Lower leaflet',
            'pep': 'Peptide atoms',
            'water': 'Water molecules',
            'ions': 'Ions',
            'water_model': 'Water model',
            'charge_before': 'System charge (before neutralization)',
            'charge_after': 'System charge (after neutralization)',
            'total_atoms': 'Total atoms',
        },
        'fr': {
            'box': 'Boîte (X×Y×Z, nm)',
            'spacing': 'Espacement (nm)',
            'apl': 'Aire par lipide (Å²)',
            'upper': 'Feuillet supérieur',
            'lower': 'Feuillet inférieur',
            'pep': 'Atomes du peptide',
            'water': 'Molécules d\'eau',
            'ions': 'Ions',
            'water_model': 'Modèle d\'eau',
            'charge_before': 'Charge du système (avant neutralisation)',
            'charge_after': 'Charge du système (après neutralisation)',
            'total_atoms': 'Atomes totaux',
        },
        'es': {
            'box': 'Caja (X×Y×Z, nm)',
            'spacing': 'Espaciado (nm)',
            'apl': 'Área por lípido (Å²)',
            'upper': 'Monocapa superior',
            'lower': 'Monocapa inferior',
            'pep': 'Átomos del péptido',
            'water': 'Moléculas de agua',
            'ions': 'Iones',
            'water_model': 'Modelo de agua',
            'charge_before': 'Carga del sistema (antes de neutralizar)',
            'charge_after': 'Carga del sistema (después de neutralizar)',
            'total_atoms': 'Átomos totales',
        },
        'pt': {
            'box': 'Caixa (X×Y×Z, nm)',
            'spacing': 'Espaçamento (nm)',
            'apl': 'Área por lipídeo (Å²)',
            'upper': 'Monocamada superior',
            'lower': 'Monocamada inferior',
            'pep': 'Átomos do peptídeo',
            'water': 'Moléculas de água',
            'ions': 'Íons',
            'water_model': 'Modelo de água',
            'charge_before': 'Carga do sistema (antes de neutralizar)',
            'charge_after': 'Carga do sistema (depois de neutralizar)',
            'total_atoms': 'Átomos totais',
        },
        'zh': {
            'box': '盒子尺寸（X×Y×Z, nm）',
            'spacing': '间距 (nm)',
            'apl': '每个脂质面积 (Å²)',
            'upper': '上层',
            'lower': '下层',
            'pep': '肽原子数',
            'water': '水分子',
            'ions': '离子',
            'water_model': '水模型',
            'charge_before': '系统电荷（中和前）',
            'charge_after': '系统电荷（中和后）',
            'total_atoms': '原子总数',
        },
    }[lang]

    lines = []
    bx = summary.get('box_x_nm')
    by = summary.get('box_y_nm')
    bz = summary.get('box_z_nm')
    if bx is not None and by is not None:
        bz_part = f'×**{bz:.3f}**' if bz is not None else ''
        lines.append(f'{labels["box"]}: **{bx:.3f}**×**{by:.3f}**{bz_part}')
    if summary.get('spacing_nm') is not None:
        lines.append(f'{labels["spacing"]}: **{summary["spacing_nm"]:.4f}**')
    if summary.get('apl_a2') is not None:
        lines.append(f'{labels["apl"]}: **{summary["apl_a2"]:.2f}**')
    composition = summary.get('composition') or {}
    upper_comp = composition.get('upper') or {}
    lower_comp = composition.get('lower') or {}
    if upper_comp:
        lines.append(f'\n**{labels["upper"]}:**')
        lines.append(_format_composition(upper_comp))
    if lower_comp:
        lines.append(f'\n**{labels["lower"]}:**')
        lines.append(_format_composition(lower_comp))
    if summary.get('n_peptide_atoms', 0) > 0:
        lines.append(f'\n{labels["pep"]}: **{summary["n_peptide_atoms"]}**')
    if summary.get('n_water', 0) > 0:
        lines.append(f'{labels["water"]}: **{summary["n_water"]}**')
        if summary.get('water_model'):
            lines.append(f'{labels["water_model"]}: **{summary["water_model"]}**')
    if summary.get('n_ions', 0) > 0:
        lines.append(f'{labels["ions"]}: **{summary["n_ions"]}**')
    if summary.get('charge_before') is not None:
        lines.append(f'{labels["charge_before"]}: **{summary["charge_before"]}**')
    if summary.get('charge_after') is not None:
        lines.append(f'{labels["charge_after"]}: **{summary["charge_after"]}**')
    if summary.get('n_atoms') is not None:
        lines.append(f'\n{labels["total_atoms"]}: **{summary["n_atoms"]}**')
    return '\n'.join(lines)


@app.post("/send_results")
async def send_results(
    request: Request,
    to_email: str = Form(...),
    lang: str = Form('en'),
    pdb: Optional[str] = Form(None),
    gro: Optional[str] = Form(None),
    topology: Optional[str] = Form(None),
    pdb_gz: Optional[UploadFile] = File(None),
    gro_gz: Optional[UploadFile] = File(None),
    topology_gz: Optional[UploadFile] = File(None),
    plot_b64: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
) -> JSONResponse:
    if lang not in ('en', 'fr', 'es', 'pt', 'zh'):
        lang = 'en'
    if not to_email or '@' not in to_email:
        return JSONResponse({'ok': False, 'error': 'Invalid email address.'}, status_code=400)
    if pdb_gz is not None:
        try:
            pdb = gzip.decompress(await pdb_gz.read()).decode('utf-8')
        except Exception:
            return JSONResponse({'ok': False, 'error': 'Failed to decompress build data.'}, status_code=400)
    if gro_gz is not None:
        try:
            gro = gzip.decompress(await gro_gz.read()).decode('utf-8')
        except Exception:
            gro = None
    if topology_gz is not None:
        try:
            topology = gzip.decompress(await topology_gz.read()).decode('utf-8')
        except Exception:
            topology = None
    if not pdb:
        return JSONResponse({'ok': False, 'error': 'No build data to send.'}, status_code=400)

    try:
        summary_data = json.loads(summary) if summary else {}
    except Exception:
        summary_data = {}

    from_addr = os.environ.get('RESEND_FROM_EMAIL', 'BILBO <bilbo@delunalab.dev>')
    site_url = str(request.base_url)
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    summary_block = _build_summary_lines(summary_data, lang)

    interpretation = {
        'en': (
            'BILBO produces a starting-point structure for molecular dynamics (MD) simulations. '
            'The output is unminimized and will have steric clashes, which is normal at this stage. '
            'Energy minimization, force field assignment, and (if not enabled here) solvation must '
            'be performed before running MD.'
        ),
        'fr': (
            'BILBO produit une structure de départ pour les simulations de dynamique moléculaire (MD). '
            'La sortie n\'est pas minimisée et présente des conflits stériques, ce qui est normal à ce stade. '
            'Une minimisation d\'énergie, l\'attribution d\'un champ de forces et (si non activée ici) '
            'la solvatation doivent être effectuées avant la MD.'
        ),
        'es': (
            'BILBO produce una estructura inicial para simulaciones de dinámica molecular (MD). '
            'La salida no está minimizada y presentará choques estéricos, lo cual es normal en esta etapa. '
            'La minimización de energía, la asignación del campo de fuerza y (si no está activada aquí) '
            'la solvatación deben realizarse antes de ejecutar la MD.'
        ),
        'pt': (
            'O BILBO produz uma estrutura inicial para simulações de dinâmica molecular (MD). '
            'A saída não é minimizada e terá choques estéricos, o que é normal neste estágio. '
            'Minimização de energia, atribuição de campo de força e (se não foi ativada aqui) solvatação '
            'devem ser realizadas antes de rodar MD.'
        ),
        'zh': (
            'BILBO 生成用于分子动力学（MD）模拟的起始结构。'
            '输出未经最小化，会存在空间冲突，这是该阶段的正常现象。'
            '在运行 MD 之前必须进行能量最小化、力场分配以及（如果此处未启用）溶剂化。'
        ),
    }[lang]

    messages = {
        'en': {
            'subject': '[BILBO] Your bilayer build is ready',
            'intro': 'Hello,\n\nYour BILBO bilayer build has been completed. The output files are attached to this message.',
            'summary_h': 'Build summary:',
            'date_label': 'Date/time',
            'interp_h': 'Interpretation note:',
            'disclaimer_h': 'Important notice:',
            'disclaimer': (
                'BILBO is currently in beta preview and proof-of-concept stage. '
                'The tool is being extensively tested and used by researchers in theoretical chemistry '
                'and biology, with the goal of releasing a more consolidated final version in the near future. '
                'All contributions are welcome. Errors, instabilities, or inconsistencies may occur; '
                'should any be identified, we kindly ask that they be reported.'
            ),
            'next': f'To start a new build, please visit: {site_url}',
            'feedback': f'To report an issue or suggest a feature, please open a ticket at {ISSUES_URL}.',
        },
        'fr': {
            'subject': '[BILBO] Votre bicouche est prête',
            'intro': 'Bonjour,\n\nVotre construction de bicouche BILBO a été finalisée. Les fichiers de sortie sont joints à ce message.',
            'summary_h': 'Résumé de la construction:',
            'date_label': 'Date/heure',
            'interp_h': 'Note d\'interprétation:',
            'disclaimer_h': 'Avis important:',
            'disclaimer': (
                'BILBO se trouve actuellement en phase de beta preview et de preuve de concept. '
                'L\'outil fait l\'objet de tests approfondis et est utilisé par des chercheurs en chimie théorique '
                'et en biologie, en vue de la mise à disposition prochaine d\'une version finale plus aboutie. '
                'Toute contribution est la bienvenue. Des erreurs, instabilités ou incohérences peuvent survenir; '
                'si elles sont constatées, nous vous prions de les signaler.'
            ),
            'next': f'Pour lancer une nouvelle construction, rendez-vous sur: {site_url}',
            'feedback': f'Pour signaler un problème ou proposer une fonctionnalité, veuillez ouvrir une issue à l\'adresse {ISSUES_URL}.',
        },
        'es': {
            'subject': '[BILBO] Su bicapa está lista',
            'intro': 'Hola,\n\nSu construcción de bicapa BILBO ha sido finalizada. Los archivos de salida se encuentran adjuntos a este mensaje.',
            'summary_h': 'Resumen de la construcción:',
            'date_label': 'Fecha/hora',
            'interp_h': 'Nota de interpretación:',
            'disclaimer_h': 'Aviso importante:',
            'disclaimer': (
                'BILBO se encuentra actualmente en fase de beta preview y prueba de concepto. '
                'La herramienta está siendo ampliamente probada y utilizada por investigadores de química teórica '
                'y biología, con vistas a poner a disposición próximamente una versión final más consolidada. '
                'Toda contribución es bienvenida. Pueden ocurrir errores, inestabilidades o inconsistencias; '
                'en caso de detectarlos, solicitamos que sean reportados.'
            ),
            'next': f'Para iniciar una nueva construcción, visite: {site_url}',
            'feedback': f'Para reportar un problema o sugerir una funcionalidad, abra una issue en {ISSUES_URL}.',
        },
        'pt': {
            'subject': '[BILBO] Sua bicamada está pronta',
            'intro': 'Olá,\n\nA construção da sua bicamada no BILBO foi concluída. Os arquivos de saída estão anexados a esta mensagem.',
            'summary_h': 'Resumo da construção:',
            'date_label': 'Data/hora',
            'interp_h': 'Nota de interpretação:',
            'disclaimer_h': 'Aviso importante:',
            'disclaimer': (
                'O BILBO encontra-se em fase de beta preview e prova de conceito. '
                'A ferramenta vem sendo amplamente testada e utilizada por pesquisadores das áreas de química teórica '
                'e biologia, com vistas à disponibilização de uma versão final mais consolidada em breve. '
                'Toda contribuição é bem-vinda. Erros, instabilidades ou inconsistências podem ocorrer; '
                'caso sejam identificados, solicitamos que sejam reportados.'
            ),
            'next': f'Para iniciar uma nova construção, acesse: {site_url}',
            'feedback': f'Para reportar um problema ou sugerir uma funcionalidade, abra uma issue em {ISSUES_URL}.',
        },
        'zh': {
            'subject': '[BILBO] 您的双层膜已就绪',
            'intro': '您好，\n\n您的 BILBO 双层膜构建已完成。输出文件已附在本邮件中。',
            'summary_h': '构建摘要：',
            'date_label': '日期/时间',
            'interp_h': '解释说明：',
            'disclaimer_h': '重要提示：',
            'disclaimer': (
                'BILBO 目前处于 beta 预览和概念验证阶段。'
                '该工具正由理论化学和生物学领域的研究人员进行充分测试与使用，旨在不久后推出更为完善的正式版本。'
                '欢迎任何形式的贡献与反馈。在使用过程中可能出现错误、不稳定或不一致的情况，'
                '如发现此类问题，敬请告知。'
            ),
            'next': f'如需启动新的构建，请访问: {site_url}',
            'feedback': f'如需报告问题或提出功能建议，请在 {ISSUES_URL} 提交 issue。',
        },
    }
    m = messages[lang]
    body_text = (
        f'{m["intro"]}\n\n'
        f'**{m["summary_h"]}**\n'
        f'{m["date_label"]}: **{timestamp}**\n'
        f'{summary_block}\n\n'
        f'**{m["interp_h"]}**\n{interpretation}\n\n'
        f'**{m["disclaimer_h"]}**\n{m["disclaimer"]}\n\n'
        f'{m["next"]}\n\n'
        f'{m["feedback"]}\n\n'
        f'{EMAIL_CLOSING[lang]}'
        f'{EMAIL_SIGNATURE}'
        f'{EMAIL_FOOTER[lang]}'
    )

    raw_files: list[tuple[str, bytes]] = [('bilbo_preview.pdb', pdb.encode('utf-8'))]
    if gro:
        raw_files.append(('bilbo_preview.gro', gro.encode('utf-8')))
    if topology:
        raw_files.append(('topol.top', topology.encode('utf-8')))
    if plot_b64:
        b64 = plot_b64.split(',', 1)[-1] if plot_b64.startswith('data:') else plot_b64
        try:
            raw_files.append(('leaflet_plot.png', base64.b64decode(b64)))
        except Exception:
            pass
    attachments, zip_contents = _pack_attachments(raw_files)
    if zip_contents:
        zip_note = {
            'en': (
                'Note: due to the size of the build, all output files have been '
                'bundled into a single archive named **bilbo_results.zip** '
                f'containing: {", ".join(zip_contents)}.'
            ),
            'fr': (
                'Note: en raison de la taille de la construction, tous les fichiers '
                'de sortie ont été regroupés dans une archive unique nommée '
                f'**bilbo_results.zip** contenant: {", ".join(zip_contents)}.'
            ),
            'es': (
                'Nota: debido al tamaño de la construcción, todos los archivos de '
                'salida se han empaquetado en un único archivo llamado '
                f'**bilbo_results.zip** que contiene: {", ".join(zip_contents)}.'
            ),
            'pt': (
                'Observação: devido ao tamanho da construção, todos os arquivos de '
                'saída foram agrupados em um único arquivo chamado '
                f'**bilbo_results.zip** contendo: {", ".join(zip_contents)}.'
            ),
            'zh': (
                f'注意：由于构建文件较大，所有输出文件已打包为单个压缩包 '
                f'**bilbo_results.zip**，其中包含：{", ".join(zip_contents)}。'
            ),
        }[lang]
        body_text = body_text.replace(
            m['intro'],
            f'{m["intro"]}\n\n{zip_note}',
            1,
        )

    payload = {
        'from': from_addr,
        'to': [to_email],
        'reply_to': 'madsondeluna@gmail.com',
        'subject': m['subject'],
        'text': body_text,
        'html': _wrap_email_html(body_text),
        'attachments': attachments,
    }
    ok, info = _resend_send(payload)
    if ok:
        return JSONResponse({'ok': True})
    return JSONResponse({'ok': False, 'error': info}, status_code=503 if 'not configured' in info else 500)


@app.post("/send_recommendation")
async def send_recommendation(
    request: Request,
    to_email: str = Form(...),
    lang: str = Form('en'),
) -> JSONResponse:
    if lang not in ('en', 'fr', 'es', 'pt', 'zh'):
        lang = 'en'
    if not to_email or '@' not in to_email:
        return JSONResponse({'ok': False, 'error': 'Invalid email address.'}, status_code=400)

    from_addr = os.environ.get('RESEND_FROM_EMAIL', 'BILBO <bilbo@delunalab.dev>')
    site_url = str(request.base_url)

    messages = {
        'en': {
            'subject': 'Someone recommends BILBO to you',
            'body': (
                'You are receiving this message because a BILBO user considered '
                'that this tool may be of interest to you.\n\n'
                'Hello,\n\n'
                'BILBO (Bilayer Lipid Builder and Organizer) is a free, open-source tool '
                'for building all-atom flat lipid bilayer membranes from PDB templates. '
                'It places proteins or peptides on or inside the membrane, producing '
                'starting-point structures for molecular dynamics (MD) simulations.\n\n'
                'Built with Python, FastAPI, NumPy, and SQLAlchemy. Runs directly in the '
                'browser, with no installation required.\n\n'
                'Available in three formats:\n'
                f'Web: {site_url}\n'
                'CLI / repo: https://github.com/madsondeluna/bilbo\n'
                'Python package: pip install bilbo-md\n\n'
                'To report an issue or suggest a feature, please open a ticket at:\n'
                f'{ISSUES_URL}\n'
                'For any further questions, contact details are provided below.\n\n'
            ),
        },
        'fr': {
            'subject': 'Quelqu\'un vous recommande BILBO',
            'body': (
                'Vous recevez ce message car une personne utilisant BILBO a estimé '
                'que cet outil pourrait vous intéresser.\n\n'
                'Bonjour,\n\n'
                'BILBO (Bilayer Lipid Builder and Organizer) est un outil gratuit et '
                'open-source pour construire des bicouches lipidiques tout-atome plates '
                'à partir de gabarits PDB. Il place des protéines ou des peptides sur ou '
                'dans la membrane, produisant des structures de départ pour les simulations '
                'de dynamique moléculaire (MD).\n\n'
                'Construit avec Python, FastAPI, NumPy et SQLAlchemy. Fonctionne directement '
                'dans le navigateur, sans aucune installation.\n\n'
                'Disponible en trois formats:\n'
                f'Web: {site_url}\n'
                'CLI / dépôt: https://github.com/madsondeluna/bilbo\n'
                'Paquet pip: pip install bilbo-md\n\n'
                'Pour signaler un problème ou proposer une fonctionnalité, veuillez ouvrir une issue:\n'
                f'{ISSUES_URL}\n'
                'Pour toute question, les coordonnées de contact figurent ci-dessous.\n\n'
            ),
        },
        'es': {
            'subject': 'Alguien le recomienda BILBO',
            'body': (
                'Recibe este mensaje porque una persona que utiliza BILBO consideró '
                'que esta herramienta podría serle de interés.\n\n'
                'Hola,\n\n'
                'BILBO (Bilayer Lipid Builder and Organizer) es una herramienta gratuita '
                'y de código abierto para construir bicapas lipídicas todo-átomo planas '
                'a partir de plantillas PDB. Coloca proteínas o péptidos sobre o dentro '
                'de la membrana, produciendo estructuras iniciales para simulaciones de '
                'dinámica molecular (MD).\n\n'
                'Construido con Python, FastAPI, NumPy y SQLAlchemy. Funciona directamente '
                'en el navegador, sin necesidad de instalación.\n\n'
                'Disponible en tres formatos:\n'
                f'Web: {site_url}\n'
                'CLI / repo: https://github.com/madsondeluna/bilbo\n'
                'Paquete pip: pip install bilbo-md\n\n'
                'Para reportar un problema o sugerir una funcionalidad, abra una issue en:\n'
                f'{ISSUES_URL}\n'
                'Para cualquier consulta, los datos de contacto se encuentran a continuación.\n\n'
            ),
        },
        'pt': {
            'subject': 'Alguém recomendou o BILBO a você',
            'body': (
                'Você recebe esta mensagem porque uma pessoa que utiliza o BILBO '
                'considerou que esta ferramenta poderia lhe ser útil.\n\n'
                'Olá,\n\n'
                'O BILBO (Bilayer Lipid Builder and Organizer) é uma ferramenta gratuita '
                'e open-source para construir bicamadas lipídicas all-atom planas a partir '
                'de templates PDB. Posiciona proteínas ou peptídeos sobre ou dentro da '
                'membrana, produzindo estruturas iniciais para simulações de dinâmica '
                'molecular (MD).\n\n'
                'Construído com Python, FastAPI, NumPy e SQLAlchemy. Roda diretamente no '
                'navegador, sem necessidade de instalação.\n\n'
                'Disponível em três formatos:\n'
                f'Web: {site_url}\n'
                'CLI / repo: https://github.com/madsondeluna/bilbo\n'
                'Pacote pip: pip install bilbo-md\n\n'
                'Para reportar um problema ou sugerir uma funcionalidade, abra uma issue em:\n'
                f'{ISSUES_URL}\n'
                'Em caso de dúvidas, os contatos estão disponíveis abaixo.\n\n'
            ),
        },
        'zh': {
            'subject': '有人向您推荐 BILBO',
            'body': (
                '您收到此邮件，是因为一位 BILBO 用户认为该工具可能对您有所帮助。\n\n'
                '您好，\n\n'
                'BILBO（Bilayer Lipid Builder and Organizer）是一款免费的开源工具，'
                '用于从 PDB 模板构建全原子平面脂质双层膜。它能在膜上或膜内放置蛋白质或肽，'
                '生成用于分子动力学（MD）模拟的起始结构。\n\n'
                '使用 Python、FastAPI、NumPy 和 SQLAlchemy 构建。可直接在浏览器中运行，无需安装。\n\n'
                '提供三种格式：\n'
                f'Web: {site_url}\n'
                'CLI / repo: https://github.com/madsondeluna/bilbo\n'
                'Python 包: pip install bilbo-md\n\n'
                '如需报告问题或提出功能建议，请在以下地址提交 issue：\n'
                f'{ISSUES_URL}\n'
                '如有任何疑问，请使用下方联系方式与我联系。\n\n'
            ),
        },
    }

    m = messages[lang]
    body_text = (
        f'{m["body"]}'
        f'{EMAIL_CLOSING[lang]}'
        f'{EMAIL_SIGNATURE}'
        f'{EMAIL_FOOTER[lang]}'
    )
    payload = {
        'from': from_addr,
        'to': [to_email],
        'reply_to': 'madsondeluna@gmail.com',
        'subject': m['subject'],
        'text': body_text,
        'html': _wrap_email_html(body_text),
    }
    ok, info = _resend_send(payload)
    if ok:
        return JSONResponse({'ok': True})
    return JSONResponse({'ok': False, 'error': info}, status_code=503 if 'not configured' in info else 500)


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
    request: Request = None,
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

        n_upper = sum(upper_counts_dict.values())
        n_lower = sum(lower_counts_dict.values())
        session_id = (request.cookies.get("_bilbo_sid") if request else None) or str(uuid.uuid4())
        try:
            _increment_stats(n_total_atoms)
        except Exception:
            pass
        upper_summary = ", ".join(f"{k}:{v}" for k, v in upper_counts_dict.items())
        lower_summary = ", ".join(f"{k}:{v}" for k, v in lower_counts_dict.items())
        totals = _get_stats()
        _send_telegram(
            f"[BILBO] New membrane built\n"
            f"Upper: {upper_summary}\n"
            f"Lower: {lower_summary}\n"
            f"Lipids: {n_upper + n_lower} | Atoms: {n_total_atoms:,}\n"
            f"Solvated: {'yes' if solvate_enabled else 'no'}\n"
            f"Session: {session_id[:8]}...\n"
            f"\n"
            f"Totals\n"
            f"Builds: {totals.get('total_builds', 0):,}\n"
            f"Atoms assembled: {totals.get('total_atoms', 0):,}\n"
            f"Unique users: {totals.get('unique_sessions', 0):,}"
        )

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
