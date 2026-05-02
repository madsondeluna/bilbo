"""Convert PDB text to GROMACS GRO format."""


def pdb_to_gro(pdb_text: str) -> str:
    lines = pdb_text.splitlines()

    box_x = box_y = box_z = 0.0
    for line in lines:
        if line.startswith("CRYST1"):
            box_x = float(line[6:15]) / 10.0
            box_y = float(line[15:24]) / 10.0
            box_z = float(line[24:33]) / 10.0
            break

    atom_lines = [ln for ln in lines if ln.startswith(("ATOM", "HETATM"))]

    gro_lines = ["BILBO membrane", f"{len(atom_lines):5d}"]
    for i, line in enumerate(atom_lines):
        resseq = int(line[22:26]) % 100000
        resname = line[17:21].strip()
        atomname = line[12:16].strip()
        serial = (i + 1) % 100000
        x = float(line[30:38]) / 10.0
        y = float(line[38:46]) / 10.0
        z = float(line[46:54]) / 10.0
        gro_lines.append(
            f"{resseq:5d}{resname:<5s}{atomname:>5s}{serial:5d}{x:8.3f}{y:8.3f}{z:8.3f}"
        )

    gro_lines.append(f"{box_x:10.5f}{box_y:10.5f}{box_z:10.5f}")
    return "\n".join(gro_lines) + "\n"
