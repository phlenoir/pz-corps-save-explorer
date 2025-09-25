#!/usr/bin/env python3
"""
find_unit_offsets.py — recherche toutes les occurrences d'un nom d'unité dans un fichier .sav
et affiche leurs offsets (hex et décimal).
"""

import argparse

def utf16le_pattern(name: str) -> bytes:
    """Convertit un nom ASCII en séquence UTF-16LE (lo=char, hi=0x00) + terminator 00 00"""
    out = bytearray()
    for ch in name:
        out.append(ord(ch))
        out.append(0x00)
    # terminateur (00 00)
    out.append(0x00)
    out.append(0x00)
    return bytes(out)

def find_all(data: bytes, pat: bytes) -> list[int]:
    offsets = []
    start = 0
    while True:
        pos = data.find(pat, start)
        if pos == -1:
            break
        offsets.append(pos)
        start = pos + 1  # continuer après pour trouver d'autres occurrences
    return offsets

def main():
    ap = argparse.ArgumentParser(description="Find all offsets of a unit name in a save file")
    ap.add_argument("savefile", help="Path to the .pzsav file")
    ap.add_argument("unit_name", help="Unit name as visible in game (ASCII)")
    args = ap.parse_args()

    with open(args.savefile, "rb") as f:
        data = f.read()

    pat = utf16le_pattern(args.unit_name)
    offs = find_all(data, pat)

    if not offs:
        print(f"No occurrence of '{args.unit_name}' found.")
    else:
        print(f"Found {len(offs)} occurrence(s) of '{args.unit_name}':")
        for o in offs:
            print(f"  - offset {o} (0x{o:x})")

if __name__ == "__main__":
    main()
