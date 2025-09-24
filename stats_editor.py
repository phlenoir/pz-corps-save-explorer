#!/usr/bin/env python3
"""
stats_editor.py — Update unit/hero stats in Panzer Corps .pzsav saves using the robust scanner.

Design goals
- Keep edits in-place (no resizing), little-endian writes
- Prefer offsets captured by the scanner (stats16_off / unit_stats_off)
- Fallback: derive hero stats offset by locating the hero's image name and
  taking the 16×u16 block that follows
- Safety: dry-run by default, backup on write

Examples
---------
# Update hero stats by name (first hero), dry-run only
python stats_editor.py --save saves/example.pzsav --units-offset 0x39ED9 \
  --unit-name "45th SdKfz  7/2" --hero-index 1 --set attack=22 movement=8

# Same but actually write back (with .bak backup)
python stats_editor.py --save saves/example.pzsav --units-offset 0x39ED9 \
  --unit-name "45th SdKfz  7/2" --hero-index 1 --set attack=22 movement=8 --write

# Update by unit index instead of name (2nd unit from offset), set defense
python stats_editor.py --save saves/example.pzsav --units-offset 0x39ED9 \
  --unit-index 2 --hero-index 1 --set defense=12 --write

"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
import shutil

from robust_unit_scanner import scan_units

# ====== Low-level LE writers ======

def set_u16_le(buf: bytearray, base_off: int, index: int, value: int) -> None:
    if value < 0 or value > 0xFFFF:
        raise ValueError(f"value out of range for u16: {value}")
    off = base_off + index * 2
    if off < 0 or off + 2 > len(buf):
        raise IndexError(f"write beyond buffer for u16 at 0x{off:x}")
    buf[off:off+2] = value.to_bytes(2, "little", signed=False)

def set_u32_le(buf: bytearray, base_off: int, index: int, value: int) -> None:
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(f"value out of range for u32: {value}")
    off = base_off + index * 4
    if off < 0 or off + 4 > len(buf):
        raise IndexError(f"write beyond buffer for u32 at 0x{off:x}")
    buf[off:off+4] = value.to_bytes(4, "little", signed=False)

# ====== Named indices ======

HERO_STAT_INDEX: Dict[str, int] = {
    # 1-based positions given earlier -> 0-based indices
    "attack": 3,
    "defense": 5,
    "initiative": 6,
    "movement": 8,
    "spotting": 10,
    "range": 12,
}

# Placeholder mapping for unit stats (u32). Adjust as your format becomes clear.
UNIT_STAT_INDEX: Dict[str, int] = {
    # "attack": 3,
    # "defense": 5,
    # "initiative": 6,
    # "movement": 8,
    # "spotting": 10,
    # "range": 12,
}

# ====== Helpers ======

def write_with_backup(path: str, data: bytes, backup_ext: str = ".bak") -> None:
    p = Path(path)
    if p.exists():
        shutil.copy2(p, p.with_suffix(p.suffix + backup_ext))
    with open(p, "wb") as f:
        f.write(data)

def parse_kv_updates(pairs: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"expected key=value, got: {item}")
        k, v = item.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if not v.isdigit():
            # allow hex like 0x12
            if v.lower().startswith("0x"):
                val = int(v, 16)
            else:
                raise ValueError(f"value must be int (dec/hex), got: {v}")
        else:
            val = int(v)
        out[k] = val
    if not out:
        raise ValueError("no updates provided")
    return out

# Try to derive hero stats16 offset if the scanner didn't record it
# Strategy: look for the hero's image C-string within the unit slice, then take the
# following 32 bytes as the 16*u16 stats block.

def find_hero_stats16_off(data: bytes, unit_start: int, unit_end: int, image_name: str) -> Optional[int]:
    # C-string bytes: name + null terminator
    key = image_name.encode("ascii", errors="ignore") + b"\x00"
    start = max(0, unit_start)
    end = min(len(data), unit_end) if unit_end else len(data)
    pos = data.find(key, start, end)
    if pos < 0:
        return None
    stats_off = pos + len(key)  # immediately after the NUL of the image name
    if stats_off + 32 <= len(data):
        return stats_off
    return None

# ====== High level API ======

def set_hero_stats(buf: bytearray, data: bytes, unit, hero, updates: Dict[str, int]) -> List[Tuple[str, int, int]]:
    """Apply updates to a hero's 16×u16 stats. Returns a list of (key, old, new)."""
    # Prefer an explicit offset captured by the scanner
    stats_off: Optional[int] = getattr(hero, "stats16_off", None)
    if stats_off is None:
        # Fallback: locate via image name within unit range
        stats_off = find_hero_stats16_off(data, getattr(unit, "start_off", 0), getattr(unit, "end_off", 0), hero.image)
        if stats_off is None:
            raise RuntimeError("Could not locate hero stats block (need scanner to record stats16_off)")

    changed: List[Tuple[str, int, int]] = []
    for k, newv in updates.items():
        idx = HERO_STAT_INDEX.get(k)
        if idx is None:
            raise KeyError(f"Unknown hero stat key: {k}")
        # read old
        old = int.from_bytes(buf[stats_off + idx*2: stats_off + idx*2 + 2], "little")
        if old == newv:
            continue
        set_u16_le(buf, stats_off, idx, newv)
        # keep Python-side cache in sync if present
        if hasattr(hero, "stats16") and idx < len(hero.stats16):
            hero.stats16[idx] = newv
        changed.append((k, old, newv))
    return changed


def set_unit_stats(buf: bytearray, unit, updates: Dict[str, int]) -> List[Tuple[str, int, int]]:
    """Apply updates to a unit's u32 stats block (mapping is placeholder)."""
    stats_off: Optional[int] = getattr(unit, "unit_stats_off", None)
    if stats_off is None:
        raise RuntimeError("Unit stats offset (unit_stats_off) not recorded by scanner")
    changed: List[Tuple[str, int, int]] = []
    for k, newv in updates.items():
        idx = UNIT_STAT_INDEX.get(k)
        if idx is None:
            raise KeyError(f"Unknown unit stat key: {k}")
        old = int.from_bytes(buf[stats_off + idx*4: stats_off + idx*4 + 4], "little")
        if old == newv:
            continue
        set_u32_le(buf, stats_off, idx, newv)
        # sync cache if present
        if hasattr(unit, "stats") and idx < len(unit.stats):
            unit.stats[idx] = newv
        changed.append((k, old, newv))
    return changed

# ====== CLI ======

def main() -> None:
    ap = argparse.ArgumentParser(description="Edit Panzer Corps .pzsav stats (hero/unit)")
    ap.add_argument("--save", required=True, help="Path to .pzsav file")
    ap.add_argument("--units-offset", required=True, help="Offset of FIRST unit (hex 0x... or decimal)")

    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument("--unit-name", help="Exact unit name to edit")
    sel.add_argument("--unit-index", type=int, help="1-based index of unit starting at --units-offset")

    ap.add_argument("--hero-index", type=int, help="1-based hero index when editing hero stats")
    ap.add_argument("--scope", choices=["hero", "unit"], default="hero", help="Which stats to edit")
    ap.add_argument("--set", nargs="+", metavar="key=value", help="Updates, e.g. attack=22 movement=8", required=True)
    ap.add_argument("--write", action="store_true", help="Actually write changes back (default: dry-run)")

    args = ap.parse_args()

    with open(args.save, "rb") as f:
        raw = bytearray(f.read())
    data = bytes(raw)  # immutable view for searches

    off = int(args.units_offset, 16) if str(args.units_offset).lower().startswith("0x") else int(args.units_offset)

    units = scan_units(data, off)
    if not units:
        raise SystemExit("No units parsed at given offset")

    if args.unit_name:
        us = [u for u in units if u.name == args.unit_name]
        if not us:
            raise SystemExit(f"Unit not found by name: {args.unit_name}")
        unit = us[0]
    else:
        idx = (args.unit_index or 1) - 1
        if idx < 0 or idx >= len(units):
            raise SystemExit("Unit index out of bounds")
        unit = units[idx]

    updates = parse_kv_updates(args._get_kwargs_dict().get('set') if hasattr(args, '_get_kwargs_dict') else args.__dict__['set'])

    changes: List[Tuple[str, int, int]] = []
    if args.scope == "hero":
        if not unit.heroes:
            raise SystemExit("Unit has no heroes")
        hidx = (args.hero_index or 1) - 1
        if hidx < 0 or hidx >= len(unit.heroes):
            raise SystemExit("Hero index out of bounds")
        hero = unit.heroes[hidx]
        changes = set_hero_stats(raw, data, unit, hero, updates)
    else:
        changes = set_unit_stats(raw, unit, updates)

    if not changes:
        print("No changes to apply (values already equal)")
        return

    print(f"Changes ({len(changes)}):")
    for k, old, new in changes:
        print(f" - {k}: {old} -> {new}")

    if args.write:
        write_with_backup(args.save, raw)
        print("Saved with backup (.bak)")
    else:
        print("Dry-run only. Use --write to persist.")

# small helper for argparse namespace (py3.11 doesn't have a built-in to dict)
setattr(argparse.Namespace, "_get_kwargs_dict", lambda self: {k: v for k, v in self._get_kwargs()})

if __name__ == "__main__":
    main()
