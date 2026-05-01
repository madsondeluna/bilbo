# BILBO: Bilayer Lipid Builder and Organizer

```
  · · · · · · · · · · · · · · · · · · · · · · ·
  | | | | | | | | | | | | | | | | | | | | | | |
  | | | | | | | | | | | | | | | | | | | | | | |
  | | | | | | | | | | | | | | | | | | | | | | |
  | | | | | | | | | | | | | | | | | | | | | | |

                  BILBO  v0.1.0
     Bilayer  Lipid  Builder and  Organizer

  | | | | | | | | | | | | | | | | | | | | | | |
  | | | | | | | | | | | | | | | | | | | | | | |
  | | | | | | | | | | | | | | | | | | | | | | |
  | | | | | | | | | | | | | | | | | | | | | | |
  · · · · · · · · · · · · · · · · · · · · · · ·
```

BILBO builds lipid bilayer membranes from PDB files and places proteins or peptides on or inside them. The two core operations are:

1. **Build**: give one or more lipid PDB files with a count each, get a bilayer.
2. **Place**: give a protein or peptide PDB, specify position and orientation, get a combined membrane + molecule system.

Output files are starting-point structures for molecular dynamics preparation. BILBO does not run minimization, does not assign force field parameters, and does not solvate the system.

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

Verify:

```bash
bilbo --version
bilbo drytest
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick start

Build a bilayer from your lipid PDB files, then place a peptide on its surface:

```bash
bilbo membrane build --upper-pdb POPE.pdb:50 --upper-pdb POPG.pdb:14 --seed 42 --output builds/my_membrane

bilbo membrane place builds/my_membrane --peptide MELITTIN.pdb --leaflet upper --orientation parallel --x 2.8 --y 2.8 --depth 0.0 --output builds/my_membrane
```

The build step produces `preview_allatom.pdb`, leaflet CSV files, and a manifest. The place step aligns the peptide to the real headgroup surface and writes `system.pdb`.

## bilbo membrane build

Builds a bilayer from PDB files. Each PDB is used as the structural template for one lipid species. The lipid ID is the uppercase stem of the filename (`POPE.pdb` → `POPE`). No database or library is required.

```bash
bilbo membrane build \
  --upper-pdb POPE.pdb:50 \
  --upper-pdb POPG.pdb:14 \
  --lower-pdb POPE.pdb:64 \
  --seed 42 \
  --spacing 0.7 \
  --bilayer-gap 6.0 \
  --output builds/my_membrane
```

**Flags:**

`--upper-pdb FILE.pdb:N` — upper leaflet species with count N. Repeat for multiple species. Required at least once.

`--lower-pdb FILE.pdb:N` — lower leaflet species with count N. Repeat for multiple species. If omitted, the lower leaflet mirrors the upper (symmetric bilayer).

`--seed INTEGER` — random seed for lipid grid placement. Same seed reproduces an identical layout. Default: `42`.

`--spacing FLOAT` — lateral distance between lipid centers in the 2D grid, in nanometers. Default: `0.7`. Values outside the range that gives 35–80 Å² area per lipid trigger a warning.

`--bilayer-gap FLOAT` — total gap at the bilayer center between the two monolayers, in Angstroms. Default: `6.0`.

`--output PATH` — directory for all output files. Created if it does not exist. Required.

**PDB validation:** each input PDB must contain more than 10 ATOM or HETATM records and must have a z-coordinate extent between 5 and 60 Angstroms. Files outside those limits are rejected before any output is written.

**Output files:**

| File | Description |
|---|---|
| `preview_allatom.pdb` | All-atom bilayer assembled by tiling lipid templates |
| `upper_leaflet.csv` | x, y positions and lipid IDs for the upper leaflet |
| `lower_leaflet.csv` | x, y positions and lipid IDs for the lower leaflet |
| `build_report.json` | Build parameters, realized counts, and template SHA-256 hashes |
| `manifest.json` | List of all files written |

**Asymmetric bilayer example:**

```bash
bilbo membrane build \
  --upper-pdb POPE.pdb:45 --upper-pdb POPG.pdb:10 --upper-pdb CL.pdb:5 \
  --lower-pdb POPE.pdb:40 --lower-pdb POPG.pdb:15 --lower-pdb CL.pdb:9 \
  --seed 7 \
  --output builds/asymmetric
```

## bilbo membrane place

Places a protein or peptide on or inside an existing bilayer built with `bilbo membrane build`. The peptide bottom is aligned to the actual headgroup surface extracted from `preview_allatom.pdb`.

```bash
bilbo membrane place BUILD_DIR \
  --peptide MELITTIN.pdb \
  --leaflet upper \
  --orientation parallel \
  --x 2.8 \
  --y 2.8 \
  --depth 0.0 \
  --output BUILD_DIR
```

**Arguments:**

`BUILD_DIR` — directory produced by `bilbo membrane build`. Must contain `build_report.json` and `preview_allatom.pdb`. Required.

**Flags:**

`--peptide PATH` — PDB file of the molecule to place. Required unless `--placement` is given.

`--placement PATH` — YAML file with a full `PeptidePlacement` descriptor. Overrides all geometric flags.

`--leaflet TEXT` — target leaflet: `upper`, `lower`, `center`, or `transmembrane`. Default: `upper`.

`--orientation TEXT` — initial orientation of the principal axis: `parallel` (along x), `perpendicular` (along z), `tilted`, or `transmembrane`. Default: `parallel`.

`--x FLOAT` — lateral x position in nanometers. Default: `0.0`.

`--y FLOAT` — lateral y position in nanometers. Default: `0.0`.

`--depth FLOAT` — insertion depth in nanometers. `0.0` places the bottommost atom at the headgroup surface. Positive values push the molecule into the membrane; negative values lift it above the surface. Default: `0.0`.

`--rotation-deg FLOAT` — in-plane rotation around z, in degrees. Default: `0.0`.

`--tilt-deg FLOAT` — tilt away from the membrane plane, in degrees. Applies when `--orientation tilted`. Default: `0.0`.

`--azimuth-deg FLOAT` — azimuthal rotation around the principal axis, in degrees. Default: `0.0`.

`--allow-overlap` — suppress the collision warning when the peptide overlaps membrane atoms. Default: off.

`--output PATH` — directory for output files. Defaults to `BUILD_DIR`.

**Output files:**

| File | Description |
|---|---|
| `system.pdb` | Combined membrane + placed molecule |
| `geometry_report.json` | Translation vector, rotation matrix, and collision count |
| `peptide_placements.json` | All placement records appended to the build |
| `build_report.json` | Updated with placement metadata |

## Secondary build modes

`bilbo membrane build` (from PDB files) is the primary interface. Two additional modes are available when a lipid library and presets are registered in the local database.

### bilbo membrane compose

Builds from a percentage composition string. Lipid IDs must be registered in the library with `bilbo lipid add`.

```bash
bilbo membrane compose \
  --upper POPE:70,POPG:20,CL:10 \
  --lipids-per-leaflet 64 \
  --output builds/ecoli_direct
```

Asymmetric:

```bash
bilbo membrane compose \
  --upper POPE:70,POPG:20,CL:10 \
  --lower POPE:50,POPG:30,CL:20 \
  --lipids-per-leaflet 64 \
  --output builds/asymmetric
```

`--upper`: upper leaflet as `LIPID:PCT` comma-separated list. Percentages are normalized to 100 automatically. Required.

`--lower`: lower leaflet. Defaults to mirror of upper.

`--force-field`: force field name for topology output. Default: `charmm36`.

`--lipids-per-leaflet`: lipids per leaflet. Required.

`--seed`: random seed. Default: `42`.

`--spacing`: lateral grid spacing in nm. Default: `0.7`.

`--bilayer-gap`: bilayer center gap in Angstroms. Default: `6.0`.

`--allatom-dir`: directory with PDB templates. Defaults to `data/examples/charmm_gui/`.

`--output`: output directory. Required.

### bilbo membrane build-preset

Builds from a named preset registered in the local library. Produces a GROMACS topology skeleton in addition to the structural preview.

```bash
bilbo membrane build-preset \
  --preset ecoli_inner_membrane_default \
  --force-field charmm36 \
  --lipids-per-leaflet 128 \
  --seed 42 \
  --output builds/ecoli_128
```

`--preset`: preset ID as registered with `bilbo preset add`. Required.

`--force-field`: force field name. Required.

`--engine`: simulation engine for topology. Currently `gromacs` only. Default: `gromacs`.

`--lipids-per-leaflet`: lipids per leaflet. Required.

`--seed`: random seed. Default: `42`.

`--spacing`: lateral grid spacing in nm. Default: `0.7`.

`--bilayer-gap`: bilayer center gap in Angstroms. Default: `6.0`.

`--ff-dir`: GROMACS force field directory name as it appears in your installation (e.g. `charmm36-jul2022.ff`). Default: `charmm36.ff`.

`--allatom-dir`: directory with PDB templates.

`--output`: output directory. Required.

This command also writes `topol.top` (GROMACS topology skeleton) and `report.md` (Markdown build summary).

## Lipid library

The lipid library stores metadata for each lipid species: headgroup class, tail lengths, net charge, force field mappings, and curation status. Library entries are required only for `membrane compose` and `membrane build-preset`. For `membrane build` (from PDB), no library is needed.

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

`curation_status` controls build eligibility for preset-based builds: only `validated` lipids enter a build. Valid values: `pending_review`, `curated`, `validated`.

### bilbo lipid list

```bash
bilbo lipid list
```

### bilbo lipid show

```bash
bilbo lipid show POPE
```

### bilbo lipid validate

Parses and validates a YAML file without writing to the database.

```bash
bilbo lipid validate data/examples/lipids/POPE.yaml
```

## Membrane presets

A preset is a named membrane composition with per-leaflet lipid percentages and metadata (organism, evidence level, references). Presets are required only for `membrane build-preset`.

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

### bilbo preset list

```bash
bilbo preset list
```

### bilbo preset show

```bash
bilbo preset show ecoli_inner_membrane_default
```

### bilbo preset validate

```bash
bilbo preset validate data/examples/presets/ecoli_inner_membrane_default.yaml
```

## Force field compatibility

### bilbo compatibility matrix

Prints which lipids in the library have mappings for each registered force field.

```bash
bilbo compatibility matrix
```

### bilbo compatibility check

```bash
bilbo compatibility check \
  --preset ecoli_inner_membrane_default \
  --force-field charmm36
```

## Extract commands

These commands import data into the local library from files on disk.

### bilbo extract lipids

```bash
bilbo extract lipids data/examples/lipids/
```

### bilbo extract presets

```bash
bilbo extract presets data/examples/presets/
```

### bilbo extract mappings

```bash
bilbo extract mappings data/examples/forcefields/charmm36_mapping.csv
```

The CSV must have columns: `lipid_id`, `force_field`, `residue_name`. Additional columns `topology_file`, `status`, and `notes` are optional.

### bilbo extract topologies

```bash
bilbo extract topologies data/examples/topologies/
```

### bilbo extract audit

```bash
bilbo extract audit
```

### bilbo extract all

```bash
bilbo extract all data/examples/
```

## Visualization

### bilbo view leaflet-map

Renders the 2D lipid grid in the terminal. Each species appears in a distinct color.

```bash
bilbo view leaflet-map builds/my_membrane
```

### bilbo view composition

Renders realized lipid counts per leaflet in the terminal.

```bash
bilbo view composition builds/my_membrane
```

### Opening in VMD

```bash
vmd builds/my_membrane/preview_allatom.pdb -e builds/my_membrane/view_vmd.tcl
```

### Opening in PyMOL

```bash
pymol builds/my_membrane/view_pymol.pml
```

## Environment variables

`BILBO_DB_PATH`: path to the SQLite database used as the local library. Default: `~/.bilbo/bilbo.db`.

```bash
export BILBO_DB_PATH=./my_project.db
```

## Data directory structure

```
data/
  examples/
    lipids/          YAML descriptors for each lipid species
    presets/         YAML files defining membrane compositions
    forcefields/     CSV files mapping lipids to force field residue names
    charmm_gui/      PDB templates (one per lipid, e.g. POPE.pdb)
    peptides/        PDB structures for test peptides
```

## Complete workflow: from PDB files to system ready for MD preparation

```bash
# Build a symmetric E. coli inner membrane from PDB templates
bilbo membrane build \
  --upper-pdb data/examples/charmm_gui/POPE.pdb:70 \
  --upper-pdb data/examples/charmm_gui/POPG.pdb:20 \
  --upper-pdb data/examples/charmm_gui/CL.pdb:10 \
  --seed 42 \
  --output builds/ecoli

# Inspect the layout
bilbo view leaflet-map builds/ecoli
bilbo view composition builds/ecoli

# Place an antimicrobial peptide on the upper leaflet surface
bilbo membrane place builds/ecoli \
  --peptide data/examples/peptides/AMP01.pdb \
  --leaflet upper \
  --orientation parallel \
  --x 2.0 --y 2.0 \
  --depth 0.0 \
  --output builds/ecoli

# Open the system in PyMOL
pymol builds/ecoli/system.pdb
```

After this, the system requires solvation, ion addition, energy minimization, and equilibration before any production MD run.

## Drytest

Runs a complete end-to-end pipeline using the bundled example data.

```bash
bilbo drytest
bilbo drytest --templates-dir /path/to/charmm_gui_pdbs
```

## Limitations

- The all-atom PDB is assembled by tiling single-lipid templates. Lateral positions come from a 2D grid and atoms are not energy-minimized. The structure will have steric clashes and is not equilibrated.
- `bilbo membrane place` uses rigid-body positioning with no clash resolution between placed molecules and membrane lipids.
- BILBO does not generate or modify force field parameters. All topology parameters must come from an external validated source.
- The `topol.top` produced by `build-preset` is a skeleton. It requires solvation, ion addition, and correct `#include` paths before `gmx grompp` can process it.
- LPS, gangliosides, ionizable lipids at non-standard pH, and ceramides with complex headgroups have no bundled descriptors.
