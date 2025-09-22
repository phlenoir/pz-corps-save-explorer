#!/usr/bin/env python3
"""
show_unit.py — uses the Robust Unit Scanner to display ONE or MORE units by name or by offset.

- Relies on robust_unit_scanner.py (contiguous 0xFF sentinels).
- Displays a readable preview of the history and derived hero characteristics.
- debug: reports non-ASCII bytes skipped before each hero.

Examples:
    # Search by name
    python show_unit.py saves/exemple.sav "45th SdKfz  7/2" --units-offset 0x39ED9

    # Directly by offset (first unit at this offset)
    python show_unit.py saves/exemple.sav --units-offset 0x39ED9

    # By offset + index (e.g., 2nd unit from the offset)
    python show_unit.py saves/exemple.sav --units-offset 0x39ED9 --index 2

    # By offset + multiple units (e.g., 3 units from the offset)
    python show_unit.py saves/exemple.sav --units-offset 0x39ED9 --count 3
"""
from __future__ import annotations
import argparse
from robust_unit_scanner import scan_units, decode_history

def main():
    p = argparse.ArgumentParser(description="Show unit(s) (robust scanner)")
    p.add_argument("savefile", help="Path to the save file (*.sav)")
    p.add_argument("unit_name", nargs="?", help="Exact unit name (UTF-16LE decoded). Optional if using offset only.")
    p.add_argument("--units-offset", required=True, help="Offset of FIRST unit (hex 0x... or decimal)")
    p.add_argument("--index", type=int, default=1, help="Index of the first unit to show after offset (default=1)")
    p.add_argument("--count", type=int, default=1, help="Number of units to show starting at index (default=1)")
    # Options d'affichage
    p.add_argument("--hist-snippet", type=int, default=160, help="Chars of history preview (default 160)")
    p.add_argument("--hist-offset", type=int, default=185, 
               help="Byte offset into history. 185 seems to work all the time")
    # Fenêtres & seuils (relais vers scan_units)
    p.add_argument("--after-name", type=int, default=None, help="Override window after name (bytes)")
    p.add_argument("--history", type=int, default=None, help="Override window for history (bytes)")
    p.add_argument("--tail", type=int, default=None, help="Override window for tail (bytes)")
    p.add_argument("--min-run", type=int, default=None, help="Min FF run length (>=4 recommended)")
    p.add_argument("--max-run", type=int, default=None, help="Max FF run length (<=16)")
    args = p.parse_args()

    with open(args.savefile, "rb") as f:
        data = f.read()

    off = int(args.units_offset, 16) if str(args.units_offset).lower().startswith("0x") else int(args.units_offset)
    print(f"[offset] using: 0x{off:x} ({off})")

    # Prépare les kwargs optionnels pour scan_units (garde None => valeurs par défaut du scanner)
    scan_kwargs = {}
    if args.after_name is not None:
        scan_kwargs['after_name_window'] = args.after_name
    if args.hist_offset is not None:
        scan_kwargs['hist_head_off'] = args.hist_offset        
    if args.history is not None:
        scan_kwargs['history_window'] = args.history
    if args.tail is not None:
        scan_kwargs['tail_window'] = args.tail
    if args.min_run is not None:
        scan_kwargs['min_run'] = args.min_run
    if args.max_run is not None:
        scan_kwargs['max_run'] = args.max_run

    # Parse une suite d'unités à partir de l'offset
    units = scan_units(data, off, **scan_kwargs)
    print(f"[scan] parsed units: {len(units)}")

    matches = []
    if args.unit_name:
        matches = [u for u in units if u.name == args.unit_name]
        if not matches:
            # Petit secours: essai trim si espaces suspects
            trimmed = args.unit_name.strip()
            if trimmed != args.unit_name:
                matches = [u for u in units if u.name == trimmed]
        if not matches:
            print(f"No unit named '{args.unit_name}' found.")
            if units[:5]:
                print("Here are a few names parsed:")
                for u in units[:5]:
                    print(" -", u.name)
            return
    else:
        # si pas de nom fourni : prendre les unités à partir de l'index demandé
        start = args.index - 1
        end = start + args.count
        if units and 0 <= start < len(units):
            matches = units[start:end]
        else:
            print("No unit found at given offset/index.")
            return

    for u in matches:
        print(f"=== {u.name} ===  @ 0x{u.start_off:x}")
        print(f"Stats: {u.stats}")
        # Dérivés par positions 1-based -> indices 0-based
        def get(idx: int):
            return u.stats[idx] if idx is not None and idx < len(u.stats) else None
        xp         = get(9)
        fuel       = get(17)
        ammo       = get(19)
        kills      = get(24)
        losses     = get(26)
        erase_inf  = get(28)
        erase_tank = get(30)
        erase_reco = get(32)
        erase_at   = get(34)
        erase_art  = get(36)
        erase_aa   = get(38)
        print(
            "       derived: "
            f"xp={xp} fuel={fuel} ammo={ammo} "
            f"kills={kills} losses={losses} erase_inf={erase_inf} "
            f"erase_tank={erase_tank} erase_reco={erase_reco} erase_at={erase_at} "
            f"erase_art={erase_art} erase_aa={erase_aa} "
        )
        preview = decode_history(u.history,offset=args.hist_offset, snippet=args.hist_snippet)
        print(f"History  : {len(u.history)} bytes | preview: {preview!r}")

        if u.heroes:
            print(f"Heroes   : {len(u.heroes)}")
            for i, h in enumerate(u.heroes, 1):
                # Dérivés par positions 1-based: 4,6,8,10,12,14 -> indices 0-based: 3,5,7,9,11,13
                def get(idx: int):
                    return h.stats16[idx] if idx is not None and idx < len(h.stats16) else None
                attack     = get(3)
                defense    = get(5)
                initiative = get(7)
                movement   = get(9)
                spotting   = get(11)
                range_     = get(13)

                print(f"  [{i}] name={h.name}  image={h.image}")
                print(f"       stats16: {h.stats16}")
                print(
                    "       derived: "
                    f"attack={attack} defense={defense} initiative={initiative} "
                    f"movement={movement} spotting={spotting} range={range_}"
                )
                if hasattr(h, 'skipped_prefix') and h.skipped_prefix:
                    print(f"       note: skipped {h.skipped_prefix} non-ASCII bytes before this hero")
        else:
            print("Heroes   : none")

        if u.citations:
            print("Citations:")
            for i, s in enumerate(u.citations, 1):
                # Commencer à la première occurrence d'un caractère imprimable (>=32)
                s2 = s
                for j, ch in enumerate(s):
                    if ord(ch) >= 32:
                        s2 = s[j:]
                        break
                print(f"  - ({i}) {s2}")
        else:
            print("Citations: none")

if __name__ == "__main__":
    main()
