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

BILBO is a command-line tool for building lipid bilayer membrane models intended for preparation of molecular dynamics (MD) simulations. It manages a local lipid library with curation status tracking, organizes membrane presets with per-leaflet composition, expands compositions into deterministic 2D leaflet layouts, generates GROMACS topology skeletons, and exports structural previews from CHARMM-GUI all-atom templates. Peptide placement over the membrane surface uses rigid geometric transforms (PCA-based axis alignment followed by rotation and translation).

BILBO does not generate force field parameters, does not run minimization, and does not produce equilibrated structures. All output files are starting-point files that require solvation, ion addition, energy minimization, and equilibration before any production simulation.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- CHARMM-GUI account for all-atom PDB templates (free registration at charmm-gui.org)
- GROMACS installation if running the topology directly

## Installation

Install from source using uv (recommended):

```bash
git clone <repository-url>
cd bilbo-md
uv sync
```

This creates a virtual environment and installs all dependencies. The `bilbo` command is available via:

```bash
uv run bilbo
```

To install the entry point globally so `bilbo` works without `uv run`:

```bash
uv pip install -e .
```

Install using pip directly:

```bash
pip install -e .
```

For development (includes pytest, ruff, mypy):

```bash
pip install -e ".[dev]"
```

Using Docker:

```bash
docker build -t bilbo-md .
docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/builds:/app/builds bilbo-md bilbo --help
```

Verify the installation:

```bash
bilbo --version
bilbo drytest
```

`bilbo drytest` runs an end-to-end pipeline using the example data bundled with the package. It requires CHARMM-GUI PDB templates in `data/examples/charmm_gui/`. If templates are missing, the command prints instructions for obtaining them.

## Interactive menu

Running `bilbo` without arguments in an interactive terminal opens an arrow-key menu. In non-interactive contexts (pipes, scripts, CI), it prints the help text instead.

## Obtaining CHARMM-GUI templates

The all-atom preview and topology generation require one PDB file per lipid species, obtained from the CHARMM-GUI Individual Lipid Molecule Library:

1. Create a free account at charmm-gui.org.
2. Navigate to Input Generator > Membrane Builder > Lipid Library.
3. Download the PDB file for each lipid in your system (e.g., POPE.pdb, POPG.pdb, CL.pdb).
4. Place all `.pdb` files in `data/examples/charmm_gui/` (or any directory passed with `--allatom-dir`).

The filename must match the residue name exactly (case-sensitive). BILBO reads the residue name from the PDB `ATOM` records, so the file POPE.pdb must contain residue POPE.

## Environment variables

`BILBO_DB_PATH`: path to the SQLite database used as the local library. Default: `~/.bilbo/bilbo.db`. Set this to use an isolated database per project:

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
    topologies/      Local .itp / .top / .rtf files for residue validation
    charmm_gui/      CHARMM-GUI all-atom PDB templates (one per lipid)
    peptides/        PDB structures and YAML descriptors for peptides
```

## Lipid library

### bilbo lipid add

Registers a lipid from a YAML descriptor file into the local library. If the lipid ID already exists, the entry is updated.

```bash
bilbo lipid add data/examples/lipids/POPE.yaml
bilbo lipid add data/examples/lipids/POPG.yaml
bilbo lipid add data/examples/lipids/CL.yaml
```

A lipid YAML descriptor contains:

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

The `curation_status` field controls build eligibility. Only lipids with `curation_status: validated` can enter a membrane build. Valid values are `pending_review`, `curated`, and `validated`.

### bilbo lipid list

Prints all lipids in the library with their curation status and force field mappings.

```bash
bilbo lipid list
```

### bilbo lipid show

Prints the full record for a single lipid.

```bash
bilbo lipid show POPE
```

### bilbo lipid validate

Parses and validates a YAML file without writing to the database. Useful for checking a new descriptor before importing it.

```bash
bilbo lipid validate data/examples/lipids/POPE.yaml
```

## Membrane presets

A preset is a named membrane composition with per-leaflet lipid percentages. Presets support asymmetric bilayers where upper and lower leaflets have different compositions.

### bilbo preset add

Registers a preset from a YAML file.

```bash
bilbo preset add data/examples/presets/ecoli_inner_membrane_default.yaml
```

A preset YAML file:

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

Percentages within each leaflet are normalized automatically. They do not need to sum to exactly 100.

### bilbo preset list

Lists all registered presets with their composition.

```bash
bilbo preset list
```

### bilbo preset show

Prints the full record for a single preset.

```bash
bilbo preset show ecoli_inner_membrane_default
```

### bilbo preset validate

Parses and validates a YAML preset without writing to the database.

```bash
bilbo preset validate data/examples/presets/ecoli_inner_membrane_default.yaml
```

## Force field compatibility

### bilbo compatibility matrix

Prints a table showing which lipids in the library have validated mappings for each force field.

```bash
bilbo compatibility matrix
```

### bilbo compatibility check

Checks whether all lipids in a preset have validated mappings for a given force field.

```bash
bilbo compatibility check --preset ecoli_inner_membrane_default --force-field charmm36
```

`--preset`: preset ID as registered in the library.
`--force-field`: force field name to check (e.g. `charmm36`).

## Extract commands

Extract commands populate the library from external data files without requiring network access.

### bilbo extract lipids

Reads all `.yaml` files in a directory and imports them as lipid descriptors.

```bash
bilbo extract lipids data/examples/lipids/
```

### bilbo extract presets

Reads all `.yaml` files in a directory and imports them as membrane presets.

```bash
bilbo extract presets data/examples/presets/
```

### bilbo extract mappings

Reads a CSV file mapping lipid IDs to force field residue names and stores the mappings in the library.

```bash
bilbo extract mappings data/examples/forcefields/charmm36_mapping.csv
```

The CSV must have columns: `lipid_id`, `force_field`, `residue_name`. Additional columns (`topology_file`, `status`, `notes`) are optional.

### bilbo extract topologies

Scans a directory of topology files (`.itp`, `.top`, `.rtf`) for `[ moleculetype ]` or `RESI` blocks to extract residue names. Results are printed and can be used to validate that a lipid's residue name appears in the force field topology.

```bash
bilbo extract topologies data/examples/topologies/
```

### bilbo extract charmm-gui-archive

Parses a locally saved HTML page from the CHARMM-GUI lipid library and extracts lipid names and categories. No network requests are made. All extracted entries are marked `pending_review`.

```bash
bilbo extract charmm-gui-archive charmm_gui_library.html --output-dir data/sources/charmm_gui/
```

To obtain the HTML file, open the CHARMM-GUI Individual Lipid Molecule Library page in a browser and save it as a complete web page.

`--output-dir`: directory where extracted metadata is written. Default: `/tmp/bilbo_charmm`.

### bilbo extract references

Reads a YAML file containing literature references and imports them into the library.

```bash
bilbo extract references data/examples/references.yaml
```

### bilbo extract audit

Audits all lipid entries in the library and reports missing fields, invalid statuses, and lipids that cannot be used in a build.

```bash
bilbo extract audit
```

### bilbo extract all

Runs all extraction steps at once from a data directory containing the standard subdirectory layout.

```bash
bilbo extract all data/examples/
```

## Membrane build

### bilbo membrane build

Builds a membrane from a registered preset. This is the main build command when you have a curated preset in the library.

```bash
bilbo membrane build --preset ecoli_inner_membrane_default --force-field charmm36 --engine gromacs --lipids-per-leaflet 128 --sorting random --seed 42 --output builds/ecoli_128
```

Flags:

`--preset`: ID of the preset registered with `bilbo preset add`. Required.

`--force-field`: Force field name. Must match a mapping registered with `bilbo extract mappings`. Required. Example: `charmm36`.

`--engine`: Simulation engine for topology output. Currently `gromacs` is the supported value. Default: `gromacs`.

`--lipids-per-leaflet`: Number of lipid molecules in each leaflet. The total system contains twice this number. Required.

`--sorting`: Spatial arrangement algorithm for lipid positions in the 2D grid. Options: `random` (fully random assignment), `domain_enriched` (groups same-type lipids into spatial domains). Default: `random`.

`--seed`: Integer seed for the random number generator. Use the same seed to reproduce an identical layout. Default: `42`.

`--output`: Directory where all build outputs are written. Created if it does not exist. Required.

`--ff-dir`: Name of the GROMACS force field directory as it appears in your GROMACS installation (e.g. `charmm36-jul2022.ff`). This name is written verbatim into the `#include` statements of `topol.top`. Default: `charmm36.ff`.

`--allatom-dir`: Custom directory containing CHARMM-GUI PDB templates. If omitted, BILBO uses `data/examples/charmm_gui/` relative to the package data directory.

### bilbo membrane compose

Builds a membrane from a direct lipid composition without requiring a preset in the library. Lipid IDs must still be registered with `bilbo lipid add`.

```bash
bilbo membrane compose --upper POPE:70,POPG:20,CL:10 --lipids-per-leaflet 64 --output builds/ecoli_direct
```

Asymmetric bilayer:

```bash
bilbo membrane compose --upper POPE:70,POPG:20,CL:10 --lower POPE:50,POPG:30,CL:20 --lipids-per-leaflet 64 --output builds/asymmetric_test
```

Flags:

`--upper`: Upper leaflet composition as a comma-separated `LIPID:PCT` list. Percentages are normalized to 100 automatically. Required.

`--lower`: Lower leaflet composition. If omitted, the lower leaflet mirrors the upper (symmetric bilayer). Optional.

`--force-field`: Force field name. Default: `charmm36`.

`--engine`: Simulation engine. Default: `gromacs`.

`--lipids-per-leaflet`: Number of lipid molecules per leaflet. Required.

`--sorting`: Spatial arrangement algorithm: `random` or `domain_enriched`. Default: `random`.

`--seed`: Random seed. Default: `42`.

`--output`: Output directory. Required.

`--allatom-dir`: Custom CHARMM-GUI template directory. Optional.

`--ff-dir`: GROMACS force field directory name. Default: `charmm36.ff`.

### Build output files

Every successful build writes the following files to the output directory:

| File | Description |
|---|---|
| `build_report.json` | Machine-readable report with preset, composition, realized counts, and warnings |
| `upper_leaflet.csv` | Grid positions and lipid assignments for the upper leaflet |
| `lower_leaflet.csv` | Grid positions and lipid assignments for the lower leaflet |
| `topol.top` | GROMACS topology skeleton with `#include` directives and `[ molecules ]` section |
| `preview_allatom.pdb` | All-atom PDB preview assembled from CHARMM-GUI templates |
| `view_vmd.tcl` | VMD startup script to visualize the preview |
| `view_pymol.pml` | PyMOL startup script to visualize the preview |
| `manifest.json` | List of all files written in the build |
| `report.md` | Human-readable Markdown summary |

The `topol.top` file is a topology skeleton only. It contains the correct `[ molecules ]` section in the same order as the coordinate file, but the system requires solvation, ion addition, energy minimization, and equilibration before any MD run.

The CRYST1 record in `preview_allatom.pdb` contains the simulation box dimensions derived from the 2D grid geometry (X and Y) and the actual atom z-coordinate range plus a 20 Å buffer (Z). This record is required by `gmx grompp`.

## Peptide library

### bilbo peptide add

Registers a peptide from a YAML descriptor file.

```bash
bilbo peptide add data/examples/peptides/AMP01.yaml
```

A peptide YAML descriptor:

```yaml
id: AMP01
name: Magainin-2
sequence: GIGKFLHSAKKFGKAFVGEIMNS
structure_file: data/examples/peptides/AMP01.pdb
structure_format: pdb
net_charge: 4
residue_count: 23
source: uniprot
curation_status: validated
references:
  - id: zasloff1987
    doi: 10.1073/pnas.84.15.5449
    source_type: doi
```

### bilbo peptide list

Lists all peptides in the library.

```bash
bilbo peptide list
```

### bilbo peptide show

Prints the full record for a single peptide.

```bash
bilbo peptide show AMP01
```

### bilbo peptide validate

Validates a peptide YAML without writing to the database.

```bash
bilbo peptide validate data/examples/peptides/AMP01.yaml
```

## Peptide placement

### bilbo membrane add-peptide

Computes the rigid-body placement of a peptide on the membrane surface using PCA-based axis alignment. The principal axis of the peptide structure is computed from all atom coordinates and aligned to the target orientation.

```bash
bilbo membrane add-peptide builds/ecoli_128 --peptide data/examples/peptides/AMP01.pdb --leaflet upper --orientation parallel --x 0.0 --y 0.0 --depth 1.8 --rotation-deg 90 --tilt-deg 0
```

`builds/ecoli_128`: path to an existing build directory containing `build_report.json`. Required argument.

`--peptide`: path to a PDB or XYZ structure file for the peptide. Optional if `--placement` is provided.

`--placement`: path to a YAML placement descriptor. If both `--peptide` and `--placement` are given, `--peptide` overrides the `input_structure` field in the descriptor.

`--leaflet`: which leaflet surface to place the peptide on. Options: `upper`, `lower`, `center`. Default: `upper`.

`--orientation`: how to align the peptide principal axis relative to the bilayer normal. Options:

- `parallel`: the principal axis lies in the membrane plane (xy-plane).
- `perpendicular`: the principal axis aligns with the bilayer normal (z-axis).
- `tilted`: the principal axis is rotated by `--tilt-deg` from the bilayer normal.
- `transmembrane`: the peptide is centered on the bilayer midplane with its axis along z.

Default: `parallel`.

`--x`, `--y`: lateral position of the peptide center of mass in nanometers. Default: `0.0` each.

`--depth`: insertion depth in nanometers from the leaflet surface toward the bilayer center. Default: `0.0`.

`--rotation-deg`: in-plane rotation of the peptide around the z-axis after alignment, in degrees. Default: `0.0`.

`--tilt-deg`: tilt angle from the bilayer normal when `--orientation tilted` is used. Default: `0.0`.

`--azimuth-deg`: azimuthal rotation around the peptide principal axis before placement. Default: `0.0`.

`--allow-overlap`: if set, placement proceeds even when the peptide overlaps with membrane atoms beyond the collision cutoff. Default: off.

`--output`: directory where placement output files are written. Defaults to the build directory.

The command writes `geometry_report.json` and `peptide_placements.json` to the output directory.

## Sources commands

These commands manage indexing of external lipid parameter sources.

### bilbo sources list

Lists all registered external sources.

```bash
bilbo sources list
```

### bilbo sources fetch

Downloads or indexes lipid metadata from an external source.

```bash
bilbo sources fetch charmm-gui --html charmm_gui_library.html
bilbo sources fetch core-set --lipids POPE,POPG,CL
```

`source`: name of the source to fetch: `charmm-gui` or `core-set`.

`--html`: path to a saved HTML file (used for `charmm-gui`).

`--lipids`: comma-separated list of lipid IDs to restrict the fetch.

`--output`: directory for raw downloaded files.

`--download`: attempt to download files. Off by default (indexing only).

`--force-fields`: comma-separated list of force fields to filter.

### bilbo sources index

Scans a local directory of downloaded source files and indexes their contents.

```bash
bilbo sources index data/sources/
```

### bilbo sources audit

Audits all entries from registered sources and reports curation gaps.

```bash
bilbo sources audit
```

### bilbo sources show

Shows all source entries for a specific lipid ID.

```bash
bilbo sources show POPE
```

## View commands

These commands render a build summary in the terminal using Rich.

### bilbo view leaflet-map

Renders the 2D lipid grid of both leaflets in the terminal. Each lipid species appears with a distinct color.

```bash
bilbo view leaflet-map builds/ecoli_128
```

### bilbo view composition

Renders a bar chart of realized lipid counts per leaflet.

```bash
bilbo view composition builds/ecoli_128
```

## Export commands

These commands generate or regenerate specific output files from an existing build.

### bilbo export allatom-preview

Regenerates the all-atom PDB preview from CHARMM-GUI templates.

```bash
bilbo export allatom-preview builds/ecoli_128
bilbo export allatom-preview builds/ecoli_128 --templates-dir /path/to/pdbs
```

`--templates-dir` / `-t`: directory containing CHARMM-GUI PDB templates. Optional; defaults to `data/examples/charmm_gui/`.

### bilbo export vmd-script

Regenerates the VMD visualization startup script.

```bash
bilbo export vmd-script builds/ecoli_128
```

To open the preview in VMD:

```bash
vmd builds/ecoli_128/preview_allatom.pdb -e builds/ecoli_128/view_vmd.tcl
```

### bilbo export pymol-script

Regenerates the PyMOL visualization startup script.

```bash
bilbo export pymol-script builds/ecoli_128
```

To open the preview in PyMOL:

```bash
pymol builds/ecoli_128/view_pymol.pml
```

### bilbo export complex-preview

Checks that peptide placement output is present and confirms the complex preview was written by `membrane add-peptide`.

```bash
bilbo export complex-preview builds/ecoli_128
```

### bilbo export manifest

Regenerates the `manifest.json` file listing all build outputs.

```bash
bilbo export manifest builds/ecoli_128
```

### bilbo export report

Exports the build report as JSON or Markdown.

```bash
bilbo export report builds/ecoli_128 --format json
bilbo export report builds/ecoli_128 --format markdown
```

`--format`: `json` or `markdown`. Default: `json`.

## Drytest

`bilbo drytest` runs a complete end-to-end pipeline using the example lipids, presets, and CHARMM-GUI templates. It is the fastest way to verify that the installation is correct.

```bash
bilbo drytest
bilbo drytest --templates-dir /path/to/charmm_gui_pdbs
```

`--templates-dir` / `-t`: directory with CHARMM-GUI PDB templates. Defaults to `data/examples/charmm_gui/`. If the directory is empty or does not exist, the command prints step-by-step instructions for obtaining templates.

## Complete workflow example

This example builds an *Escherichia coli* inner membrane model with 128 lipids per leaflet and exports it for GROMACS.

Step 1: Import lipid descriptors.

```bash
bilbo lipid add data/examples/lipids/POPE.yaml
bilbo lipid add data/examples/lipids/POPG.yaml
bilbo lipid add data/examples/lipids/CL.yaml
```

Step 2: Import force field mappings.

```bash
bilbo extract mappings data/examples/forcefields/charmm36_mapping.csv
```

Step 3: Register the membrane preset.

```bash
bilbo preset add data/examples/presets/ecoli_inner_membrane_default.yaml
```

Step 4: Check compatibility before building.

```bash
bilbo compatibility check --preset ecoli_inner_membrane_default --force-field charmm36
```

Step 5: Build the membrane.

```bash
bilbo membrane build --preset ecoli_inner_membrane_default --force-field charmm36 --engine gromacs --lipids-per-leaflet 128 --sorting random --seed 42 --output builds/ecoli_128
```

Step 6: Inspect the result.

```bash
bilbo view leaflet-map builds/ecoli_128
bilbo view composition builds/ecoli_128
```

Step 7: Open in VMD.

```bash
vmd builds/ecoli_128/preview_allatom.pdb -e builds/ecoli_128/view_vmd.tcl
```

Step 8 (optional): Place an antimicrobial peptide on the upper leaflet surface.

```bash
bilbo membrane add-peptide builds/ecoli_128 --peptide data/examples/peptides/AMP01.pdb --leaflet upper --orientation parallel --depth 1.8 --rotation-deg 90
```

Step 9 (optional): Open the complex in PyMOL.

```bash
pymol builds/ecoli_128/view_pymol.pml
```

## Curation workflow

Lipids move through three curation stages before they are eligible for a build:

1. `pending_review`: the entry was imported from an external source or created manually. Fields may be incomplete or unverified.
2. `curated`: a curator has reviewed the residue name, charge, tail lengths, and references. The entry is complete but not yet confirmed against a topology file.
3. `validated`: the residue name has been confirmed in a local topology file and all required fields are present. Only this status allows the lipid to enter a build.

Use `bilbo extract audit` to identify all lipids that are not yet buildable and the specific fields that need attention.

## Limitations

BILBO generates structural previews and topology skeletons, not simulation-ready systems. The following are outside the current scope:

- The all-atom PDB is assembled by tiling CHARMM-GUI single-lipid templates. Lateral positions are assigned from the 2D grid and atoms are not optimized. The structure will have clashes and is not equilibrated.
- The `topol.top` file contains `#include` directives pointing to the force field and per-lipid `.itp` files. The paths assume a standard GROMACS installation. If your `charmm36.ff` directory has a different name, pass `--ff-dir` with the correct name.
- Peptide placement uses rigid-body transforms with no clash resolution and no force field assignment for the peptide.
- LPS, gangliosides, ionizable lipids, and ceramides with complex headgroups are outside the current scope.
- Mixed-resolution systems (atomistic peptide on a coarse-grained membrane, or vice versa) are flagged with a warning but not resolved.
- BILBO does not generate or modify force field parameters. All topology parameters must come from an external validated source.
