#!/usr/bin/env python3
"""Patch BILBO topol.top to include protein topology from pdb2gmx output.
Also rebuilds system.pdb by replacing heavy-atom protein with the
H-enriched version produced by pdb2gmx (protein_with_h.pdb).
"""
import re
import pathlib

# Known non-protein residue names in BILBO system files.
# Anything not in this set is treated as a protein/peptide residue.
_NON_PROT = {
    # lipids
    "POPE", "POPG", "POPC", "DPPC", "DPPE", "DPPG", "DPPS",
    "BSM", "CHOL", "SAPI", "CL",
    # solvent / ions (CHARMM36 residue names)
    "SOL", "TIP3", "SOD", "CLA", "POT", "MG", "CAL", "ZN",
    "NA", "CL", "K",
}

# ── Extract protein.itp from protein_topol.top ────────────────────────────────
prot_top = pathlib.Path("protein_topol.top").read_text()

m = re.search(r'(\[ moleculetype \].*?)(?=\[ system \])', prot_top, re.S)
if not m:
    raise SystemExit("ERROR: could not find [ moleculetype ] in protein_topol.top")
protein_itp = m.group(1)
# Strip water/ion #include lines added by pdb2gmx (BILBO topol.top includes them)
protein_itp = re.sub(r'; Include water topology\s*\n#include[^\n]*tip3p[^\n]*\n', '', protein_itp)
protein_itp = re.sub(r'#ifdef POSRES_WATER.*?#endif\n?', '', protein_itp, flags=re.S)
protein_itp = re.sub(r'; Include topology for ions\s*\n#include[^\n]*ions[^\n]*\n', '', protein_itp)
protein_itp = protein_itp.rstrip() + "\n"
pathlib.Path("protein.itp").write_text(protein_itp)

mol_m = re.search(r'\[ moleculetype \]\s*\n(?:;[^\n]*\n)*(\S+)', prot_top)
if not mol_m:
    raise SystemExit("ERROR: could not parse molecule name from protein_topol.top")
prot_mol_name = mol_m.group(1)

# ── Patch topol.top ───────────────────────────────────────────────────────────
top = pathlib.Path("topol.top").read_text()

# Insert #include "protein.itp" right after the lipid topologies comment
top = re.sub(
    r'(; Lipid molecule topologies\n)',
    r'\1#include "protein.itp"\n',
    top, count=1
)

# Insert protein entry before the first solvent/ion in [ molecules ].
# BILBO writes system.pdb in order: lipids -> protein -> ions -> water.
SOLVENT_RE = re.compile(r'^(SOL|SOD|CLA|NA|CL|K|MG|CA)\s', re.MULTILINE)
mol_sec = re.search(r'(\[ molecules \]\s*\n; molecule-type\s+count\s*\n)(.*)', top, re.S)
if not mol_sec:
    raise SystemExit("ERROR: could not find [ molecules ] section in topol.top")

header = mol_sec.group(1)
mol_body = mol_sec.group(2)
first_sv = SOLVENT_RE.search(mol_body)
prot_line = f"{prot_mol_name:<16}1\n"
if first_sv:
    pos = first_sv.start()
    mol_body = mol_body[:pos] + prot_line + mol_body[pos:]
else:
    mol_body = mol_body + prot_line

top = top[:mol_sec.start()] + header + mol_body
pathlib.Path("topol.top").write_text(top)
print(f"Patched topol.top: added {prot_mol_name} 1 to [ molecules ]")
print(f"Wrote protein.itp ({len(protein_itp)} bytes)")

# ── Rebuild system.pdb with H-enriched protein ───────────────────────────────
prot_h_path = pathlib.Path("protein_with_h.pdb")
if not prot_h_path.exists():
    print("WARNING: protein_with_h.pdb not found; system.pdb not rebuilt.")
else:
    prot_h_lines = [
        ln for ln in prot_h_path.read_text().splitlines()
        if ln.startswith(("ATOM", "HETATM"))
    ]
    sys_lines = pathlib.Path("system.pdb").read_text().splitlines()
    new_sys: list[str] = []
    prot_inserted = False
    for ln in sys_lines:
        if ln.startswith(("ATOM", "HETATM")):
            rn = ln[17:21].strip()
            if rn not in _NON_PROT:
                if not prot_inserted:
                    new_sys.extend(prot_h_lines)
                    prot_inserted = True
                continue  # drop original heavy-atom protein line
        new_sys.append(ln)

    # Renumber ATOM/HETATM serials (cosmetic; GROMACS ignores them).
    # Use modulo 100000 to keep 5-char field valid for large systems.
    serial = 1
    renumbered: list[str] = []
    for ln in new_sys:
        if ln.startswith(("ATOM", "HETATM")):
            ln = ln[:6] + f"{serial % 100000:5d}" + ln[11:]
            serial += 1
        renumbered.append(ln)

    pathlib.Path("system.pdb").write_text("\n".join(renumbered) + "\n")
    print(f"Rebuilt system.pdb: replaced protein heavy atoms with "
          f"{len(prot_h_lines)} atoms (including H)")
