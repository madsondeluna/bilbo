# BILBO: Bilayer Lipid Builder and Organizer

<p align="center">
  <img src="bilbo-brand-kit/logotypes/bilbo-logotype-amber.svg" alt="BILBO" width="320">
</p>

BILBO builds flat lipid bilayer membranes from all-atom PDB templates, places proteins or peptides on or inside them, optionally solvates the system with explicit water and ions, and exports a self-contained GROMACS MD package (CHARMM36 force field bundled, MDP files included, run script included). The output is a ready-to-minimize starting structure.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
git clone <repository-url>
cd bilbo
uv sync
uv pip install -e .
```

Verify the installation:

```bash
bilbo --version
bilbo drytest
```

For development (adds pytest, ruff, mypy):

```bash
pip install -e ".[dev]"
```

## How BILBO works

Building a membrane in BILBO takes two inputs:

1. **Lipid PDB templates**: one all-atom PDB file per lipid species. BILBO uses the 3D coordinates in each file as the structural template for that species. You supply these files; BILBO does not generate them.
2. **Counts per leaflet**: how many of each species go in the upper leaflet and the lower leaflet.

BILBO then:

- Arranges the lipids on a 2D rectangular grid, one cell per lipid.
- Gives each lipid a random azimuthal rotation around the membrane normal (Z axis).
- Stacks the two leaflets back-to-back to form the bilayer, with the tails pointing toward the center.
- Writes the coordinates as a PDB file, a CSV of lateral positions, and a JSON build report.

The result is an unminimized structure. It will have steric clashes and is not suitable for simulation without energy minimization. This is normal and expected: BILBO provides a starting configuration, not an equilibrated system.

### Where to get lipid PDB templates

The most common source is [CHARMM-GUI](https://charmm-gui.org) (Membrane Builder, "Download single lipid" option). Each downloaded file provides one lipid species in the CHARMM36 force field. Alternatively, use any all-atom lipid structure from the PDB, Lipid21 (AMBER), or Slipids (GROMOS). The filename stem becomes the lipid ID: `POPE.pdb` is loaded as `POPE`.

BILBO rejects a template if it has fewer than 10 ATOM/HETATM records or if its Z-coordinate extent is outside 5-60 Å (too flat or implausibly long for a single lipid).

## Quick start

```bash
# Build a symmetric bilayer with two lipid species
bilbo membrane build \
  --upper-pdb POPE.pdb:50 \
  --upper-pdb POPG.pdb:14 \
  --seed 42 \
  --output builds/my_membrane

# Place a peptide on the upper leaflet surface
bilbo membrane place builds/my_membrane \
  --peptide MELITTIN.pdb \
  --leaflet upper \
  --orientation parallel \
  --x 2.8 --y 2.8 \
  --depth 0.0 \
  --output builds/my_membrane

# Visualize
pymol builds/my_membrane/system.pdb
```

Expected terminal output after `membrane build`:

```
APL-weighted grid spacing: 0.796 nm
All-atom preview: builds/my_membrane/preview_allatom.pdb (8064 atoms)
Build complete (symmetric): builds/my_membrane
  upper: 64 lipids  lower: 64 lipids
```

Expected terminal output after `membrane place`:

```
System PDB: builds/my_membrane/system.pdb (8072 atoms)
Peptide 'MELITTIN' placed in builds/my_membrane
```

## bilbo membrane build

Builds a bilayer directly from PDB files. No database or library is required.

```
bilbo membrane build [OPTIONS]
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--upper-pdb FILE.pdb:N` | TEXT | required | One lipid species for the upper leaflet with count N. Repeat for each species. |
| `--lower-pdb FILE.pdb:N` | TEXT | mirrors upper | One lipid species for the lower leaflet. If omitted, the lower leaflet is identical to the upper. |
| `--seed` | INTEGER | 42 | Random seed for grid placement and per-lipid azimuthal rotation. Same seed reproduces an identical structure. |
| `--sorting` | TEXT | random | Lipid arrangement: `random` (uniform random placement), `domain_enriched` (same species grouped in contiguous blocks), or `stripe` (alternating horizontal bands, A-B-A-B). |
| `--spacing` | FLOAT | APL-weighted | Lateral distance between lipid centers in nm. Computed automatically from composition when omitted. |
| `--bilayer-gap` | FLOAT | 2.5 | Total gap at the bilayer center between tail terminals of opposing leaflets, in Angstroms. |
| `--output` | PATH | required | Output directory. Created if it does not exist. |

**Output files:**

| File | Description |
|---|---|
| `preview_allatom.pdb` | All-atom bilayer (visual inspection only, not minimized) |
| `upper_leaflet.csv` | x, y positions (nm) and lipid ID for each lipid in the upper leaflet |
| `lower_leaflet.csv` | x, y positions (nm) and lipid ID for each lipid in the lower leaflet |
| `build_report.json` | Build parameters, realized counts, SHA-256 hashes of templates |
| `manifest.json` | List of all files written |

**About `--bilayer-gap`:** this parameter sets the vacuum gap between the terminal tail atoms of the two opposing leaflets before minimization. A value of 2.5 Å (default) gives a compact starting structure. Larger values (up to 10 Å) increase separation and reduce initial clashes at the bilayer center. The final equilibrated bilayer thickness is determined by the simulation force field, not by this parameter.

**About `--sorting`:** `random` distributes species uniformly across the grid, which is the physically correct starting configuration for a well-mixed bilayer. `domain_enriched` groups identical species in blocks, suitable as a starting point for domain segregation studies. `stripe` arranges species in alternating horizontal bands (A-B-A-B row pattern), useful for Lo/Ld phase separation studies where multiple domain interfaces are desired.

## bilbo membrane place

Places a protein or peptide on or inside an existing bilayer built with `membrane build`. The molecule is anchored to the actual headgroup surface extracted from `preview_allatom.pdb`, not to a hard-coded Z value.

```
bilbo membrane place BUILD_DIR [OPTIONS]
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `BUILD_DIR` | PATH | required | Directory from `membrane build`. Must contain `build_report.json` and `preview_allatom.pdb`. |
| `--peptide` | PATH | required* | PDB file of the molecule to place. |
| `--placement` | PATH | | YAML file with a full placement descriptor. Overrides all geometric flags. |
| `--leaflet` | TEXT | upper | Target leaflet: `upper`, `lower`, `center`, or `transmembrane`. |
| `--orientation` | TEXT | parallel | Orientation of the molecular principal axis: `parallel` (along X), `perpendicular` (along Z), `tilted`, or `transmembrane`. |
| `--x` | FLOAT | 0.0 | Lateral position in nm along X. |
| `--y` | FLOAT | 0.0 | Lateral position in nm along Y. |
| `--depth` | FLOAT | 0.0 | Insertion depth in nm. `0.0` places the bottommost atom at the headgroup surface. Positive values push the molecule deeper into the membrane; negative values lift it above the surface. |
| `--rotation-deg` | FLOAT | 0.0 | In-plane rotation around Z in degrees, applied after axis alignment. |
| `--tilt-deg` | FLOAT | 0.0 | Tilt angle in degrees away from the membrane plane. Only applies when `--orientation tilted`. |
| `--azimuth-deg` | FLOAT | 0.0 | Rotation around the molecular principal axis in degrees. |
| `--allow-overlap` | flag | off | Suppress the collision warning when the molecule overlaps membrane atoms. |
| `--output` | PATH | BUILD_DIR | Output directory. |

*Required unless `--placement` is given.

**Output files:**

| File | Description |
|---|---|
| `system.pdb` | Combined bilayer and placed molecule |
| `geometry_report.json` | Translation vector, rotation matrix, tilt/rotation angles, collision count |
| `build_report.json` | Updated with placement metadata |

**How orientations work:**

- `parallel`: the molecular principal axis (longest dimension, computed by SVD) is aligned with X. The molecule lies flat on the membrane surface. Use this for amphipathic helices, beta-sheets, or any molecule that binds laterally.
- `perpendicular`: the principal axis is aligned with Z. The molecule stands upright, normal to the membrane. Use this for single-pass transmembrane helices or rod-shaped molecules.
- `tilted`: the principal axis is first aligned with X, then tilted by `--tilt-deg` toward Z. Use this for helices that insert at an angle.
- `transmembrane`: equivalent to `perpendicular`, intended for full transmembrane proteins.

**How depth works:**

`--depth 0.0` places the bottommost atom of the rotated molecule exactly at the headgroup surface ($z_\text{max}$ of upper-leaflet atoms in `preview_allatom.pdb`). Positive depth values push the molecule downward by that many nanometers, into the hydrophobic core. A typical shallow amphipathic helix uses `--depth 0.0` to `--depth 0.3`. A deeply inserted helix may use `--depth 1.0` or more.

**Placing multiple copies:**

Each `membrane place` invocation adds one molecule. To place multiple copies, run the command once per copy with different `--x` and `--y` values pointing to the same `BUILD_DIR`. Each run overwrites `system.pdb` with all placed molecules accumulated so far and appends a record to `build_report.json`.

## Examples

### Example 1: single-lipid pure DPPC membrane

The simplest possible case: one species, symmetric bilayer, 128 lipids per leaflet.

```bash
bilbo membrane build \
  --upper-pdb DPPC.pdb:128 \
  --seed 42 \
  --output builds/dppc_pure
```

The lower leaflet is automatically set to 128 DPPC molecules, mirroring the upper. Grid spacing is computed from the DPPC reference APL of 64.3 Å², giving $d = \sqrt{64.3}/10 = 0.802$ nm.

```
APL-weighted grid spacing: 0.802 nm
All-atom preview: builds/dppc_pure/preview_allatom.pdb (46208 atoms)
Build complete (symmetric): builds/dppc_pure
  upper: 128 lipids  lower: 128 lipids
```

### Example 2: four-species asymmetric bilayer

An asymmetric bilayer has different compositions in the two leaflets. This is biologically common: for example, in eukaryotic plasma membranes the outer leaflet is enriched in PC and sphingomyelin while the inner leaflet contains PE, PS, and PI. Each species is specified with its own `--upper-pdb` or `--lower-pdb` flag.

```bash
bilbo membrane build \
  --upper-pdb POPC.pdb:50 \
  --upper-pdb POPE.pdb:20 \
  --upper-pdb DPPC.pdb:20 \
  --upper-pdb CHOL.pdb:10 \
  --lower-pdb POPE.pdb:40 \
  --lower-pdb POPS.pdb:25 \
  --lower-pdb POPG.pdb:20 \
  --lower-pdb CL.pdb:15 \
  --seed 42 \
  --bilayer-gap 1.0 \
  --output builds/asymmetric_euk
```

Because the two leaflets have different mean APL values, BILBO will report a projected-area mismatch warning in the terminal if the difference exceeds 10%. This is informational: it means the two leaflets have different lateral packing densities, which generates curvature stress in the unminimized structure and will relax during equilibration.

### Example 3: membrane with multiple peptide copies at controlled positions and depths

This example sets up a study of three copies of an antimicrobial peptide (melittin) at different lateral positions, insertion depths, and in-plane rotations.

```bash
# Step 1: build the membrane
bilbo membrane build \
  --upper-pdb POPE.pdb:45 \
  --upper-pdb POPG.pdb:13 \
  --upper-pdb CL.pdb:6 \
  --seed 42 \
  --bilayer-gap 1.0 \
  --output builds/melittin_study

# Step 2: surface-bound copy at the center of the box
bilbo membrane place builds/melittin_study \
  --peptide MELITTIN.pdb \
  --leaflet upper \
  --orientation parallel \
  --x 3.2 --y 3.2 \
  --depth 0.0 \
  --rotation-deg 0 \
  --output builds/melittin_study

# Step 3: second copy shifted laterally, rotated 120 degrees
bilbo membrane place builds/melittin_study \
  --peptide MELITTIN.pdb \
  --leaflet upper \
  --orientation parallel \
  --x 1.5 --y 1.5 \
  --depth 0.0 \
  --rotation-deg 120 \
  --output builds/melittin_study

# Step 4: third copy inserted 0.5 nm into the hydrophobic core
bilbo membrane place builds/melittin_study \
  --peptide MELITTIN.pdb \
  --leaflet upper \
  --orientation parallel \
  --x 5.0 --y 2.0 \
  --depth 0.5 \
  --rotation-deg 240 \
  --output builds/melittin_study
```

After step 4, `builds/melittin_study/system.pdb` contains the bilayer with all three copies. `build_report.json` has three `peptide_placements` entries, each recording the translation vector, rotation matrix, depth, and collision count with membrane atoms.

### Example 4: transmembrane helix

Place a helix perpendicular to the membrane, spanning from the lower to the upper leaflet. Use `--leaflet transmembrane` with `--orientation transmembrane` and set depth to position the helix at the center of the bilayer.

```bash
bilbo membrane build \
  --upper-pdb POPC.pdb:64 \
  --seed 42 \
  --output builds/tm_study

bilbo membrane place builds/tm_study \
  --peptide TM_HELIX.pdb \
  --leaflet transmembrane \
  --orientation transmembrane \
  --x 3.0 --y 3.0 \
  --depth 0.0 \
  --output builds/tm_study
```

## Complete workflow with visualization

```bash
# 1. Build the membrane
bilbo membrane build \
  --upper-pdb POPE.pdb:45 \
  --upper-pdb POPG.pdb:13 \
  --upper-pdb CL.pdb:6 \
  --seed 42 \
  --bilayer-gap 1.0 \
  --output builds/ecoli

# 2. Check the layout before placing anything
bilbo view leaflet-map builds/ecoli
bilbo view composition builds/ecoli

# 3. Place a peptide
bilbo membrane place builds/ecoli \
  --peptide MELITTIN.pdb \
  --leaflet upper \
  --orientation parallel \
  --x 3.0 --y 3.0 \
  --depth 0.0 \
  --output builds/ecoli

# 4. Open in PyMOL
pymol builds/ecoli/system.pdb
```

PyMOL commands for a quick colored view by lipid species:

```python
hide everything
show spheres, resn POPE or resn POPG or resn CL
color orange, resn POPE
color red, resn POPG
color marine, resn CL
show surface, chain P
color lime, chain P
zoom all
```

After visual inspection, proceed to MD. The fastest path is the **Download MD package** button in the web interface, which generates a self-contained ZIP with CHARMM36 bundled and a `gmx.sh` run script. For manual control, use the pipeline in the [Typical manual GROMACS pipeline](#typical-manual-gromacs-pipeline) section.

## Web interface

BILBO ships a browser-based interface that runs the same build pipeline as the CLI but requires no terminal commands. It is useful for exploring compositions interactively before committing to a script.

### Running locally

```bash
pip install -e ".[web]"
uvicorn web.app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in a browser.

### Deploying on Render

The repository includes a `render.yaml` that configures a Docker-based web service.

1. In the Render dashboard, click **New + > Web Service**.
2. Select **Build and deploy from a Git repository** and connect the `bilbo` repository.
3. Render detects `render.yaml` automatically and fills in all fields. Confirm: runtime Docker, plan Free, region Oregon.
4. Click **Create Web Service**. The first build takes 3-5 minutes. The service is ready when the logs show `Your service is live`.

The deployed URL has the form `https://<service-name>.onrender.com`. To change it: open the service in the Render dashboard, go to **Settings**, and edit the **Service Name** field. The new name must be globally unique across Render. For a custom domain (e.g. `bilbo.yourdomain.com`), add it under **Custom Domain** and point a CNAME record in your DNS to the current `onrender.com` address.

Subsequent deploys are automatic: every push to `main` triggers a new build.

### Persistent usage stats (Neon PostgreSQL)

The web interface tracks usage stats (builds, atoms assembled, unique users). By default these are stored in a local SQLite file (`web/stats.db`). On Render, the filesystem resets on every deploy, so the stats are lost unless you connect a persistent database.

To persist stats across deploys, create a free project on [Neon](https://neon.tech), copy the connection string from the project dashboard (**Connection string** card), and add it as an environment variable in the Render service:

```
DATABASE_URL=postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

The app detects `DATABASE_URL` automatically on startup, creates the tables if they do not exist, and uses PostgreSQL from that point on. No code changes or migrations are required.

### Species membrane presets

The web interface provides 17 curated membrane presets accessible via the "Load membrane preset" selector. Compositions are in mol% of total phospholipid and represent symmetric bilayers unless noted. All acyl chain variants use generic CHARMM36 templates (POPE, POPC, etc.) as proxies for the in-vivo acyl chain diversity. Post-translational lipid modifications, glycolipids, LPS, membrane proteins, and asymmetric leaflet distributions are not modeled.

**Gram-negative bacteria**

| Species | POPE | DPPE | POPG | DPPG | CL | Other |
|---|---|---|---|---|---|---|
| *Escherichia coli* K-12 | 45 | 30 | 12 | 8 | 5 | |
| *Salmonella* Typhimurium | 43 | 29 | 12 | 8 | 8 | |
| *Klebsiella pneumoniae* | 45 | 30 | 11 | 7 | 7 | |
| *Pseudomonas aeruginosa* PAO1 | 50 | 23 | 11 | 6 | 10 | |
| *Pseudomonas syringae* DC3000 | 42 | 23 | 13 | 7 | 10 | POPC 5 |
| *Xanthomonas campestris* | 38 | 22 | 14 | 8 | 12 | POPC 6 |
| *Ralstonia pseudosolanacearum* | 38 | 22 | 14 | 8 | 15 | POPC 3 |
| *Acinetobacter baumannii* | 45 | 25 | 14 | 8 | 8 | |
| *Helicobacter pylori* | 18 | 12 | 10 | 5 | 10 | POPS 5, SAPI 5, CHOL 35\* |

\* Cholesterol glucosides (~25% of total native lipid) approximated as free CHOL.

**Gram-positive bacteria**

| Species | POPE | DPPE | POPG | DPPG | CL | Other |
|---|---|---|---|---|---|---|
| *Bacillus subtilis* (phospholipids only) | 35 | 30 | 15 | 12 | 8 | |
| *Mycobacterium tuberculosis* (inner membrane) | 15 | 10 | 7 | 4 | 14 | SAPI 35\*, POPC 15 |

\* Glycolipids (~30% native total) and L-PG omitted from *B. subtilis*. SAPI used as proxy for phosphatidylinositol mannosides (PIM2/PIM6) in *M. tuberculosis*.

**Mammalian membranes**

| Membrane | POPC | POPE | POPS | SAPI | BSM | CHOL | CL |
|---|---|---|---|---|---|---|---|
| Mammalian plasma (simplified symmetric) | 25 | 20 | 8 | 5 | 12 | 30 | |
| Human erythrocyte (average bilayer) | 22 | 15 | 8 | 1 | 14 | 40 | |
| Mitochondrial outer membrane (MOM) | 50 | 30 | 5 | 5 | | 5 | 5 |
| Mitochondrial inner membrane (MIM) | 40 | 35 | 3 | 5 | | | 17 |
| Endoplasmic reticulum | 55 | 25 | 5 | 10 | | 5 | |
| *S. cerevisiae* plasma membrane | 17 | 20 | 30 | 18 | | 15\* | |

\* Ergosterol approximated as CHOL.

Erythrocyte and mitochondrial inner membrane compositions are based on Radhakrishnan & McConnell (PNAS, 1998) and Paradies et al. (Cells, 2019), respectively.

### Inputs

**Leaflet composition**

Add one row per lipid species. Each row has three fields:

- **Library select**: pick a lipid ID from the bundled library (POPE, POPC, POPG, POPS, DPPC, DPPE, DPPG, DPPS, CHOL, BSM, SAPI, CL). BILBO uses its own PDB template and CHARMM36 ITP for the selected species.
- **Upload PDB**: alternatively, upload a custom PDB template. The filename stem becomes the lipid ID.
- **Count**: number of molecules for that species in that leaflet.

The **Symmetric** checkbox copies the upper leaflet composition to the lower leaflet automatically. Uncheck it to define an asymmetric bilayer.

**Build settings**

| Field | Default | Description |
|---|---|---|
| Seed | 42 | Random seed for grid placement and azimuthal rotation. |
| Bilayer gap (A) | 2.5 | Vacuum gap at the bilayer center between opposing tail terminals. |
| Sorting | random | `random`: uniform placement. `domain_enriched`: species grouped in blocks. `stripe`: alternating horizontal bands (A-B-A-B). |
| Tilt angle (deg) | 0 | Global tilt of each lipid away from the membrane normal. 0 = upright. Use 10-30 for gel-phase or tilt-defect studies. Each lipid receives a random azimuthal tilt direction. |
| Spacing (nm) | auto | Grid spacing. Leave blank to compute automatically from APL-weighted composition. |
| Box side (nm) | auto | X and Y box dimensions. Leave blank to compute from the grid. |

**Peptide/protein (optional)**

Upload a PDB file to place a molecule on or inside the membrane. Options:

| Field | Default | Description |
|---|---|---|
| Leaflet | upper | Target leaflet: `upper`, `lower`, `center`, or `transmembrane`. |
| Orientation | parallel | Axis alignment: `parallel` (along X), `perpendicular` (along Z), `tilted`, `transmembrane`. |
| X / Y (nm) | center | Lateral position. Defaults to box center for a single replica. |
| Depth (nm) | 0.0 | Insertion depth from the headgroup surface. Positive values push into the hydrophobic core. |
| Rotation (deg) | 0 | In-plane rotation around Z after axis alignment. |
| Replicas | 1 | Number of copies to place. Multiple copies are distributed randomly in XY. |

**Solvation (optional)**

Check **Solvate** to add explicit water and bulk ions around the membrane. Options:

| Field | Default | Description |
|---|---|---|
| Water model | TIP3P | Water geometry: TIP3P, SPC, SPC/E, or TIP4P. |
| Box Z (nm) | auto | Total simulation box height. Leave blank to use the default water layer thickness of 3 nm per side. Minimum enforced: membrane thickness + 2 nm per side. |
| Ion conc. (mM) | 150 | NaCl concentration for bulk solvation ions (Na+ and Cl-). |
| Peptide charge | 0 | Net charge of the placed peptide, used to compute the neutralizing ion count. Upload a peptide PDB to calculate this automatically. |

**Counter-ions at headgroup (optional)**

This checkbox adds cation counter-ions positioned at the phosphate plane of anionic lipids. The ion count is computed automatically from the anionic lipid composition: for each anionic lipid (POPG, POPS, CL, etc.) the stoichiometric number of cations needed to neutralize the leaflet charge is calculated. The checkbox is disabled when the composition contains no anionic lipids.

Available ions: Na+, Ca2+, Mg2+, K+.

### Outputs

After clicking **Build membrane**, BILBO returns:

- **Download PDB**: all-atom bilayer, with optional peptide and water/ions.
- **Download GRO**: the same structure in GROMACS GRO format (coordinates in nm, periodic box on the last line). Use directly with `gmx grompp`.
- **Download topology**: a `topol.top` with `#include` directives for each lipid species.
- **Download MD package**: a self-contained ZIP archive ready to run with GROMACS. See below.

A build summary panel shows atom counts, water molecule count, ion counts, and any warnings (e.g., box Z too small, leaflet area mismatch).

### MD package (recommended for GROMACS users)

The **Download MD package** button generates a ZIP archive that contains everything needed to run a complete GROMACS simulation pipeline with no additional downloads:

| File | Description |
|---|---|
| `system.pdb` | Membrane coordinates (and solvent/ions if solvated) |
| `topol.top` | Complete GROMACS topology |
| `charmm36.ff/` | Full CHARMM36 force field (MacKerell lab, Feb 2026, CGenFF 5.0) |
| `em.mdp` | Energy minimization parameters |
| `nvt.mdp` | NVT equilibration (semiisotropic pressure, CHARMM36-compatible) |
| `npt.mdp` | NPT equilibration |
| `prod.mdp` | Production MD |
| `gmx.sh` | Shell script that runs the full EM → NVT → NPT → production workflow |
| `patch_topology.py` | (only when a peptide is present) Patches `topol.top` after `pdb2gmx` |

Before downloading, set the simulation parameters in the panel below the download buttons:

| Parameter | Default | Description |
|---|---|---|
| Production (ns) | 100 | Length of the production trajectory |
| Temperature (K) | 310.15 | Reference temperature for NVT and NPT |
| Equilibration (ps) | 100 | Duration of each equilibration stage (NVT and NPT) |
| Output freq. (ps) | 10 | How often coordinates and energies are written |

To run after extracting the ZIP:

```bash
unzip bilbo_md_package.zip
cd md_package
chmod +x gmx.sh
bash gmx.sh
```

The `chmod +x gmx.sh` step is required once to make the script executable. GROMACS 2021 or newer must be installed and `gmx` must be in `PATH`. No other dependencies are required.

### Typical manual GROMACS pipeline

If you prefer to manage the simulation setup yourself, use the PDB, GRO, and topology files directly:

```bash
# 1. Convert PDB to GRO (skip if you downloaded the GRO)
gmx editconf -f system.pdb -o system.gro

# 2. Solvate (skip if you used BILBO solvation)
gmx solvate -cp system.gro -cs spc216.gro -o solvated.gro -p topol.top

# 3. Add neutralizing ions
gmx grompp -f em.mdp -c solvated.gro -p topol.top -o ions.tpr -maxwarn 2
echo SOL | gmx genion -s ions.tpr -o ionized.gro -p topol.top -pname NA -nname CL -neutral -conc 0.15

# 4. Energy minimization
gmx grompp -f em.mdp -c ionized.gro -p topol.top -o em.tpr
gmx mdrun -v -deffnm em

# 5. NVT equilibration
gmx grompp -f nvt.mdp -c em.gro -r em.gro -p topol.top -o nvt.tpr
gmx mdrun -deffnm nvt

# 6. NPT equilibration
gmx grompp -f npt.mdp -c nvt.gro -r nvt.gro -t nvt.cpt -p topol.top -o npt.tpr
gmx mdrun -deffnm npt

# 7. Production
gmx grompp -f prod.mdp -c npt.gro -t npt.cpt -p topol.top -o prod.tpr
gmx mdrun -deffnm prod
```

For the force field, the MD package ZIP includes CHARMM36 automatically. For manual setup, download `charmm36-feb2026.ff.tgz` from [mackerell.umaryland.edu](http://mackerell.umaryland.edu/charmm_ff.shtml) and place the `.ff` directory alongside `topol.top`.

## Secondary build modes

`bilbo membrane build` requires no library. The two modes below use a local SQLite database of lipid metadata and preset compositions.

### bilbo membrane compose

Specify composition as percentages rather than absolute counts. BILBO converts percentages to integer counts using the largest-remainder method (see Scientific background). Lipid IDs must be registered with `bilbo lipid add`.

```bash
bilbo membrane compose \
  --upper POPE:70,POPG:20,CL:10 \
  --lipids-per-leaflet 64 \
  --output builds/ecoli_compose
```

Asymmetric example:

```bash
bilbo membrane compose \
  --upper POPE:70,POPG:20,CL:10 \
  --lower POPE:50,POPG:30,CL:20 \
  --lipids-per-leaflet 64 \
  --output builds/ecoli_asym
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--upper` | TEXT | required | Upper leaflet as `LIPID:PCT,...`. Percentages normalize to 100. |
| `--lower` | TEXT | mirrors upper | Lower leaflet composition. |
| `--force-field` | TEXT | charmm36 | Force field name for topology output. |
| `--lipids-per-leaflet` | INTEGER | required | Lipids per leaflet. |
| `--seed` | INTEGER | 42 | Random seed. |
| `--spacing` | FLOAT | APL-weighted | Grid spacing in nm. |
| `--bilayer-gap` | FLOAT | 6.0 | Inter-leaflet gap in Angstroms. |
| `--allatom-dir` | PATH | data/examples/charmm_gui/ | Directory with PDB templates. |
| `--output` | PATH | required | Output directory. |

### bilbo membrane build-preset

Build from a named preset stored in the library. Produces a `topol.top` GROMACS topology skeleton in addition to the structural files.

```bash
# First register the preset
bilbo preset add data/examples/presets/ecoli_inner_membrane_default.yaml

# Then build
bilbo membrane build-preset \
  --preset ecoli_inner_membrane_default \
  --force-field charmm36 \
  --lipids-per-leaflet 128 \
  --seed 42 \
  --output builds/ecoli_preset
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--preset` | TEXT | required | Preset ID as registered with `bilbo preset add`. |
| `--force-field` | TEXT | required | Force field name. |
| `--engine` | TEXT | gromacs | Simulation engine. Currently `gromacs` only. |
| `--lipids-per-leaflet` | INTEGER | required | Lipids per leaflet. |
| `--seed` | INTEGER | 42 | Random seed. |
| `--spacing` | FLOAT | APL-weighted | Grid spacing in nm. |
| `--bilayer-gap` | FLOAT | 6.0 | Inter-leaflet gap in Angstroms. |
| `--ff-dir` | TEXT | charmm36.ff | GROMACS force field directory (e.g. `charmm36-jul2022.ff`). |
| `--allatom-dir` | PATH | | Directory with PDB templates. |
| `--output` | PATH | required | Output directory. |

This command also writes `topol.top` and `report.md`. The topology skeleton includes `#include` directives for the force field and one `.itp` file per unique lipid species. It requires solvation, ion addition, and correct paths before `gmx grompp` can process it.

## Lipid library

The lipid library stores metadata for each species: IUPAC name, lipid class, headgroup, tail composition, net charge, force field mappings, curation status, and literature references. Library entries are only needed for `membrane compose` and `membrane build-preset`. For `membrane build` from PDB files, no library is required.

### bilbo lipid add

```bash
bilbo lipid add data/examples/lipids/POPE.yaml
```

A lipid YAML descriptor:

```yaml
id: POPE
name: 1-palmitoyl-2-oleoyl-sn-glycero-3-phosphoethanolamine
lipid_class: glycerophospholipid
headgroup: PE
net_charge: 0
curation_status: validated
source: charmm_gui
tails:
  sn1:
    carbon: 16
    unsaturation: 0
  sn2:
    carbon: 18
    unsaturation: 1
force_fields:
  charmm36:
    force_field: charmm36
    lipid_id: POPE
    residue_name: POPE
    topology_file: lipid36.itp
    status: validated
references:
  - id: klauda2010
    doi: 10.1021/jp101759q
    source_type: doi
```

`curation_status` controls build eligibility: only `validated` lipids enter a preset build. Valid values: `pending_review`, `curated`, `validated`.

### Other lipid commands

```bash
bilbo lipid list                                    # list all lipids in the library
bilbo lipid show POPE                               # show metadata for one species
bilbo lipid validate data/examples/lipids/POPE.yaml # validate without writing to database
```

## Membrane presets

A preset is a named composition with per-leaflet lipid percentages and biological metadata (organism, membrane type, evidence level, references).

### bilbo preset add

```bash
bilbo preset add data/examples/presets/ecoli_inner_membrane_default.yaml
```

```yaml
id: ecoli_inner_membrane_default
description: Generic Escherichia coli inner membrane model
organism: Escherichia coli
membrane_type: bacterial_inner_membrane
symmetry: symmetric
leaflets:
  upper:
    POPE: 70
    POPG: 20
    CL: 10
  lower:
    POPE: 70
    POPG: 20
    CL: 10
evidence_level: curated
references:
  - id: dowhan1997
    doi: 10.1146/annurev.biochem.66.1.199
    source_type: doi
```

### Other preset commands

```bash
bilbo preset list                                                      # list all presets
bilbo preset show ecoli_inner_membrane_default                         # show one preset
bilbo preset validate data/examples/presets/ecoli_inner_membrane_default.yaml
```

## Force field compatibility

```bash
bilbo compatibility matrix                          # which lipids have mappings per force field
bilbo compatibility check \
  --preset ecoli_inner_membrane_default \
  --force-field charmm36
```

## Extract commands

Batch-import data into the library from files on disk.

```bash
bilbo extract lipids    data/examples/lipids/         # import all lipid YAMLs
bilbo extract presets   data/examples/presets/        # import all preset YAMLs
bilbo extract mappings  data/examples/forcefields/charmm36_mapping.csv
bilbo extract topologies data/examples/topologies/
bilbo extract audit                                   # report library state
bilbo extract all       data/examples/               # run all of the above
```

The force field mapping CSV must have columns `lipid_id`, `force_field`, `residue_name`. Optional columns: `topology_file`, `status`, `notes`.

## Visualization

```bash
bilbo view leaflet-map  builds/my_membrane   # 2D grid colored by species in the terminal
bilbo view composition  builds/my_membrane   # realized counts per leaflet in the terminal
```

Open in PyMOL:

```bash
pymol builds/my_membrane/system.pdb
```

Open in VMD:

```bash
vmd builds/my_membrane/system.pdb
```

## Environment variables

`BILBO_DB_PATH`: path to the SQLite database. Default: `~/.bilbo/bilbo.db`. Set this to keep different projects in separate databases.

```bash
export BILBO_DB_PATH=./my_project.db
```

## Drytest

Runs a complete end-to-end pipeline with bundled example data and reports pass or fail for each stage.

```bash
bilbo drytest
bilbo drytest --templates-dir /path/to/charmm_gui_pdbs
```

## Scientific background

### Grid construction

For each leaflet BILBO constructs a 2D rectangular grid of $N$ lipid positions. The grid has $n_x = \lceil\sqrt{N}\rceil$ columns and $n_y = \lceil N / n_x \rceil$ rows. The center of cell $(i, j)$ is:

$$x_{i,j} = i \cdot d + d/2, \quad y_{i,j} = j \cdot d + d/2$$

where $d$ is the grid spacing in nanometers. Coordinates in PDB outputs are in Angstroms ($\times 10$).

### APL-weighted grid spacing

When `--spacing` is omitted, BILBO computes $d$ from the composition-weighted mean area per lipid (APL):

$$\bar{A} = \frac{\sum_i n_i \cdot \text{APL}_i}{\sum_i n_i}, \quad d = \frac{\sqrt{\bar{A}}}{10} \text{ nm}$$

summing over all lipid counts across both leaflets. This places each lipid center at the mean projected footprint for that composition in the liquid-crystalline $L_\alpha$ phase. When any species is absent from the reference table, BILBO prints a warning and uses $d = 0.7$ nm.

APL reference values (303 K, $L_\alpha$ phase, from MD simulations validated against X-ray and neutron diffraction):

| Lipid | Full name | APL (Å²) | Source |
|-------|-----------|----------|--------|
| DPPC  | 1,2-dipalmitoyl-sn-glycero-3-phosphocholine | 64.3 | Kucerka et al. Biophys J. 2011;101:1828 |
| DMPC  | 1,2-dimyristoyl-sn-glycero-3-phosphocholine | 60.6 | Klauda et al. J Phys Chem B. 2010;114:7830 |
| DOPC  | 1,2-dioleoyl-sn-glycero-3-phosphocholine | 72.5 | Kucerka et al. Biophys J. 2011;101:1828 |
| DOPE  | 1,2-dioleoyl-sn-glycero-3-phosphoethanolamine | 65.7 | Venable et al. J Chem Theory Comput. 2014;10:1397 |
| POPE  | 1-palmitoyl-2-oleoyl-sn-glycero-3-phosphoethanolamine | 56.6 | Kucerka et al. Biophys J. 2011;101:1828 |
| POPC  | 1-palmitoyl-2-oleoyl-sn-glycero-3-phosphocholine | 68.3 | Kucerka et al. Biophys J. 2011;101:1828 |
| POPG  | 1-palmitoyl-2-oleoyl-sn-glycero-3-phospho-(1'-rac-glycerol) | 65.0 | Venable et al. J Chem Theory Comput. 2014;10:1397 |
| POPS  | 1-palmitoyl-2-oleoyl-sn-glycero-3-phosphoserine | 55.5 | Mukhopadhyay et al. Biophys J. 2004;86:1601 |
| CL    | cardiolipin (1,3-bis(sn-3'-phosphatidyl)-sn-glycerol) | 130.0 | Dahlberg. J Phys Chem B. 2007;111:7194 |
| TOCL  | 1,1',2,2'-tetraoleoyl cardiolipin | 130.0 | Dahlberg. J Phys Chem B. 2007;111:7194 |

Cardiolipin (CL) has two phosphate groups and four acyl chains and is counted as one molecule; its APL of 130 Å² reflects the full molecular footprint.

### Per-lipid azimuthal rotation

Each lipid in the grid receives a random azimuthal rotation $\theta \sim U(0, 2\pi)$ around Z before placement. The template is first centered on its XY centroid $(\bar{x}, \bar{y})$, then rotated and translated to the grid cell center $(c_x, c_y)$:

$$x' = \cos\theta \cdot (x_0 - \bar{x}) - \sin\theta \cdot (y_0 - \bar{y}) + c_x$$
$$y' = \sin\theta \cdot (x_0 - \bar{x}) + \cos\theta \cdot (y_0 - \bar{y}) + c_y$$

The pseudorandom generator is `random.Random(seed)`, isolated from Python's global state. Identical `(seed, composition, N)` triples always produce identical structures. The Z coordinate is normalized so the terminal tail atom sits at $z_\text{gap}$ from the bilayer center, with sign flipped for the lower leaflet:

$$z = z_\text{flip} \cdot (z_0 - z_\text{tail} + z_\text{gap})$$

### Inter-species clash detection

After tiling, BILBO scans for steric clashes between atoms of different lipid species in the same leaflet. Clashes between atoms of the same species are not reported because they arise from tiling and resolve during energy minimization regardless of composition. The algorithm uses a 3D bounding-box prefilter to reduce the candidate set before computing full pairwise distances with NumPy. Inter-leaflet pairs are excluded automatically because their Z ranges do not overlap. The output counts clashing residue pairs (not atom pairs) and reports the first five with their minimum interatomic distances.

A high clash count with a small minimum distance (e.g. < 0.5 Å) between specific species suggests the grid spacing is too small for that composition. Increase `--spacing` or let BILBO compute it automatically from APL.

### Leaflet area balance

For asymmetric bilayers, BILBO checks whether the two leaflets have compatible projected areas:

$$\text{mismatch} = \frac{|N \cdot \bar{A}_\text{upper} - N \cdot \bar{A}_\text{lower}|}{\max(\ldots)} \times 100\%$$

A mismatch above 10% generates a warning with the recommended lipid count for the smaller leaflet to equalize areas. In simulation, a persistent area difference causes lateral membrane stress and can produce artificial curvature.

### Composition expansion: largest-remainder method

`membrane compose` and `membrane build-preset` convert percentage compositions to integer counts. Each species $i$ receives $\lfloor p_i \cdot N / 100 \rfloor$ lipids; the deficit to reach $N$ total is distributed one unit at a time to the species with the largest fractional remainder. Ties break alphabetically. This minimizes the maximum absolute rounding error across all species.

### Peptide placement algorithm

1. **Principal axis**: the molecular principal axis is computed from SVD of the mean-centered coordinate matrix. The first right singular vector gives the direction of maximum spatial variance.

2. **Rodrigues rotation**: the principal axis is rotated onto the target direction using the Rodrigues formula:

$$R = I + K + K^2 \frac{1 - \cos\alpha}{\sin^2\alpha}$$

where $K$ is the skew-symmetric matrix of $\hat{u} \times \hat{v}$ and $\alpha$ is the angle between source and target vectors. The antiparallel case ($\cos\alpha \approx -1$) uses the reflection $R = 2\hat{w}\hat{w}^T - I$.

3. **Surface anchoring**: the headgroup surface Z is extracted from `preview_allatom.pdb` as the maximum Z of upper-leaflet atoms. The Z offset applied to the molecule is:

$$\Delta z = z_\text{surface} - z_\text{min} - d_\text{ins}$$

where $z_\text{min}$ is the minimum Z of the rotated molecule and $d_\text{ins}$ is the insertion depth in Angstroms.

4. **Collision count**: all peptide-membrane atom pairs below 2.0 Å are counted. The count and minimum distance are recorded in `build_report.json`.

## Data directory structure

```
data/
  examples/
    lipids/          YAML descriptors for each lipid species
    presets/         YAML compositions for named membrane models
    forcefields/     CSV files mapping lipids to force field residue names
    charmm_gui/      PDB templates (one per lipid, e.g. POPE.pdb)
    peptides/        PDB structures for test peptides
```

## Force field and GROMACS pipeline validation

The CHARMM36 lipid templates, ITP files, water model files, ion files, topology generator, and MDP parameter templates were validated through a full end-to-end GROMACS simulation pipeline. The pipeline was exercised by submitting a DPPC:CHL1 3:1 bilayer (24+8 lipids per leaflet) through the `/api/build` and `/api/md_package` endpoints using the FastAPI test client, extracting the resulting ZIP package, and running each GROMACS step from `gmx editconf` through energy minimization.

### Bugs found and fixed

**Missing CHL1.itp.** The web interface example uses `CHL1.pdb` as the cholesterol template, producing lipid ID `CHL1`. The topology included `CHL1.itp`, which did not exist. Fixed by creating `data/ff/charmm36_lipids/CHL1.itp` as an alias of `CHOL.itp` with the moleculetype name changed from `CHOL` to `CHL1`.

**SOL and NA/CL moleculetypes not defined.** After `gmx solvate`, GROMACS appended `SOL` entries to `[ molecules ]` in `topol.top`. After `gmx genion`, it appended `NA` and `CL` entries. Neither was defined because `write_gromacs_topology` did not emit `#include` directives for water or ion ITPs. Fixed by adding `#include "charmm36.ff/tip3p.itp"` and `#include "charmm36.ff/ions.itp"` to the generated topology.

**Truncated DPPC.pdb in web examples.** The file `web/static/examples/DPPC.pdb` contained only 50 atoms (a partial template) while the CHARMM36 DPPC ITP defines 130 atoms. This caused `gmx grompp` to abort with "number of coordinates does not match topology". Fixed by replacing the file with the full 130-atom CHARMM-GUI template.

**nstcalcenergy/nstenergy mismatch.** The NVT, NPT, and production MDP templates did not set `nstcalcenergy`. GROMACS defaults it to 100. When `output_freq_ps` is set to values such as 0.5 ps (yielding `nstenergy = 250` steps), 250 is not a multiple of 100 and `gmx grompp` raises a fatal error. Fixed by adding `nstcalcenergy = 100` to all three templates and computing `nstcalcenergy = gcd(100, nstenergy)` dynamically in the MDP generators so that the divisibility constraint is always satisfied regardless of the output frequency requested.

**Incorrect APL reference for CHL1/CHOL causing grid spacing fallback.** `APL_REFERENCE` in `apl_check.py` was missing entries for CHL1, CHOL, DPPE, DPPG, DPPS, BSM, SM, SAPI, TOCL. When any species in a leaflet is absent from the table, `weighted_spacing` returns `None` and the builder falls back to a fixed spacing of 0.7 nm. For a DPPC:CHL1 3:1 bilayer, this spacing is too small: lipids from adjacent cells overlap, producing severe steric clashes in the starting structure. Energy minimization cannot resolve them and converges to `Fmax = inf`. Fixed by adding all missing species to `APL_REFERENCE` with CHARMM36 estimates or literature values.

**CHOL.pdb atom order mismatch.** In `data/examples/charmm_gui/CHOL.pdb`, atoms at sequential positions 2, 3, and 4 were O3/H3'/H3. The CHARMM36 ITP (both `CHOL.itp` and `CHL1.itp`) lists them in the order H3/O3/H3'. GROMACS assigns force field parameters positionally: a mismatched order silently assigns the O3 charge and Lennard-Jones parameters to the H3 atom and vice versa, corrupting the electrostatics of the hydroxyl group without any error message. Fixed by reordering lines 2-4 in CHOL.pdb so each atom name matches the ITP position. The residue name in CHOL.pdb was also corrected from `CHOL` to `CHL1` to match the residue name used in the ITP `[ atoms ]` section.

**NON_PROT set incomplete.** The Python snippet in the generated `gmx.sh` script that extracts protein residues for `pdb2gmx` filtering (the `has_peptide` branch) did not include `CHL1` in the `NON_PROT` exclusion set. CHL1 residues would be passed to `pdb2gmx` and cause it to fail. Fixed by adding `CHL1` to `NON_PROT` in both `_gmx_sh` and `patch_topology.py`.

### Data integrity test suite

The file `tests/test_lipid_data_integrity.py` contains automated checks that run as part of the standard `pytest` suite. These tests catch the classes of bugs above before they reach a user's simulation.

**PDB/ITP consistency** (parametrized over all 12 lipid species in `data/examples/charmm_gui/`):

- `test_itp_exists_for_pdb`: every PDB template has a matching ITP in `data/ff/charmm36_lipids/`. CHOL is aliased to CHL1.itp.
- `test_atom_count_pdb_matches_itp`: the number of ATOM records in the first residue of the PDB (after `_load_template` filtering) equals the number of entries in the ITP `[ atoms ]` section. A mismatch causes `gmx grompp` to abort.
- `test_atom_name_order_pdb_matches_itp`: the atom name at each sequential position is the same in the PDB and the ITP. A mismatch causes GROMACS to assign wrong force field parameters silently.
- `test_residue_name_pdb_matches_itp`: the residue name in the PDB matches the residue name used in the ITP `[ atoms ]` section. CL is skipped: its ITP residue name is `TLCL1` (5 characters), which cannot be represented in the 4-character PDB residue field; `gmx grompp` issues a warning but does not fail.

**Water and ion ITPs**:

- `test_water_itp_exists`: `tip3p.itp`, `spc.itp`, and `spce.itp` are present in `data/ff/charmm36_base/`.
- `test_ion_itp_exists`: `ions.itp` is present in `data/ff/charmm36_base/`.
- `test_water_itp_has_sol_moleculetype`: each water ITP defines the `SOL` moleculetype, which is what `gmx solvate` appends to `[ molecules ]`.
- `test_ions_itp_has_na_and_cl`: `ions.itp` defines both `NA` and `CL` moleculetypes, which `gmx genion` appends.

**Topology includes**:

- `test_topology_includes_water_and_ions`: the `topol.top` generated by `write_gromacs_topology` contains `#include` directives for `tip3p.itp` and `ions.itp`.

**APL reference completeness**:

- `test_apl_reference_covers_all_shipped_lipids`: every lipid with a PDB template in `data/examples/charmm_gui/` has an entry in `APL_REFERENCE`. A missing entry causes the grid spacing fallback to 0.7 nm.

**MDP parameter consistency**:

- `test_mdp_nstcalcenergy_set`: `nvt.mdp`, `npt.mdp`, and `prod.mdp` all declare `nstcalcenergy`, preventing the divisibility error at `gmx grompp` time.

### CL residue name note

The cardiolipin template `data/examples/charmm_gui/CL.pdb` uses `CL` as the PDB residue name. The CHARMM36 ITP (`CL.itp`) uses `TLCL1` as the residue name in its `[ atoms ]` section, but `TLCL1` is five characters and cannot be stored in the four-character PDB residue field without truncation. GROMACS generates a residue-name mismatch warning during `gmx grompp` but does not fail; atom names and their sequential order are correct, so force field parameters are assigned correctly. The mismatch appears in trajectory residue labels but does not affect simulation energetics.

## Limitations

- The all-atom PDB is assembled by tiling single-lipid templates. Each template is rotated azimuthally but not otherwise modified. The structure contains steric clashes and is not energy-minimized. It is suitable only for visual inspection and as a starting point for minimization.

- The inter-species clash detector flags clashes between different lipid species. It is a diagnostic for inadequate grid spacing, not a geometry optimizer. Intra-species clashes are not reported by design.

- `bilbo membrane place` applies rigid-body positioning. It does not resolve clashes between the placed molecule and membrane lipids. Use `--allow-overlap` to suppress the warning when testing geometries.

- BILBO does not generate or modify force field parameters. Topology parameters must come from an external validated source (CHARMM-GUI, Lipid21, Slipids, etc.).

- The `topol.top` from `build-preset` is a skeleton. It needs solvation, ion addition, and correct `#include` paths before `gmx grompp` can process it.

- The `--bilayer-gap` parameter is a clash-avoidance buffer, not a physical bilayer thickness. Do not interpret inter-leaflet distances in the unminimized structure.

- LPS, gangliosides, ionizable lipids at non-standard pH, and ceramides with complex headgroups have no bundled descriptors.
