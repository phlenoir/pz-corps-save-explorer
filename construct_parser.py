#!/usr/bin/env python3
"""
Robust unit scanner (no RepeatUntil) — avec contrôles d'offset et HISTOIRE sûre.

Mises à jour clés :
- On s'arrête STRICTEMENT à la **première sentinelle** (run de 0xFF) après chaque bloc.
- Les sentinelles peuvent avoir une longueur **variable (>=4 et <=16)**.
- L'**histoire** n'est pas supposée être séparée par `00 00` ; on ne la découpe PAS
  sur des nulls, on la lit telle quelle jusqu'à la première run de 0xFF.
- Modes debug améliorés : hexdump, aperçu des runs, distances et **extrait lisible** de l'histoire.

Usage :
  # Debug de l'offset + runs + extrait d'histoire
  python robust_unit_scanner.py --save saves/exemple.sav --units-offset 0x39ED9 --debug --dump 200

  # Lister
  python robust_unit_scanner.py --save saves/exemple.sav --units-offset 0x39ED9 --list 5

  # Chercher une unité précise
  python robust_unit_scanner.py --save saves/exemple.sav --units-offset 0x39ED9 --name "45th SdKfz  7/2"
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from typing import List, Tuple

# ------------------ constantes ------------------
MIN_FF_RUN = 4
MAX_FF_RUN = 16

# Fenêtres par défaut (surchargeables par CLI)
MAX_AFTER_NAME_TO_SENT16 = 4096      # octets max entre fin du nom et 1ère run FF
MAX_HISTORY_TO_SENT04    = 256_000   # taille max de l'histoire
MAX_TAIL_TO_SENT08       = 512_000   # taille max de la zone héros+citations
MAX_HEROES               = 3

# ------------------ dataclasses ------------------
@dataclass
class Hero:
    name: str
    type: int
    image: str
    stats16: List[int]

@dataclass
class Unit:
    name: str
    history: bytes
    heroes: List[Hero]
    citations: List[str]
    raw_tail_bytes: bytes  # le tail brut (héros+citations) avant découpe
    start_off: int
    end_off: int

# ------------------ helpers encodage ------------------

def read_utf16le_cstr(data: bytes, off: int) -> Tuple[str, int]:
    """Lit une C-string UTF-16LE (ASCII+00 répétés) terminée par 0x0000 à partir de off.
    Retourne (string, new_off). Lève ValueError si invalide."""
    out = []
    i = off
    n = len(data)
    while True:
        if i + 1 >= n:
            raise ValueError("EOF while reading UTF-16LE string")
        lo, hi = data[i], data[i+1]
        if lo == 0x00 and hi == 0x00:
            i += 2
            break
        if hi != 0x00 or not (0x20 <= lo <= 0x7E or lo == 0x09):
            raise ValueError("Invalid UTF-16LE sequence for unit name (expect ASCII+00)")
        out.append(chr(lo))
        i += 2
    return ("".join(out), i)

# ------------------ recherches sentinelles ------------------

def find_next_ff_run(data: bytes, start: int, max_advance: int,
                     min_run: int = MIN_FF_RUN, max_run: int | None = MAX_FF_RUN) -> tuple[int, int]:
    """Trouve à partir de `start` (dans la fenêtre `max_advance`) la première run de 0xFF.
    Retourne (pos, len) ou (-1, 0) si non trouvée.
    """
    end = min(len(data), start + max_advance)
    i = start
    while i < end:
        if data[i] != 0xFF:
            i += 1
            continue
        j = i
        while j < end and data[j] == 0xFF:
            j += 1
        run_len = j - i
        if run_len >= min_run and (max_run is None or run_len <= max_run):
            return i, run_len
        i = j  # saute cette run et continue
    return -1, 0


def list_ff_runs(data: bytes, start: int, lookahead: int, min_run: int = MIN_FF_RUN, max_run: int | None = MAX_FF_RUN, limit: int = 10) -> list[tuple[int,int]]:
    out = []
    end = min(len(data), start + lookahead)
    i = start
    while i < end and len(out) < limit:
        if data[i] != 0xFF:
            i += 1
            continue
        j = i
        while j < end and data[j] == 0xFF:
            j += 1
        run_len = j - i
        if run_len >= min_run and (max_run is None or run_len <= max_run):
            out.append((i, run_len))
        i = j
    return out

# ------------------ outils debug ------------------

def hexdump_slice(data: bytes, start: int, length: int = 200, width: int = 16) -> str:
    end = min(len(data), start + length)
    out_lines = []
    for off in range(start, end, width):
        chunk = data[off:off+width]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciip = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        out_lines.append(f"0x{off:08x}  {hexpart:<{width*3}}  |{asciip}|")
    return "\n".join(out_lines)

# ------------------ parsing héros & citations ------------------

def take_cstring_ascii(buf: bytes, start: int) -> Tuple[str, int]:
    i = buf.find(b"\x00", start)
    if i < 0:
        return buf[start:].decode("ascii", errors="ignore"), len(buf)
    return buf[start:i].decode("ascii", errors="ignore"), i + 1


def parse_heroes_from_tail(tail: bytes, max_heroes: int = MAX_HEROES) -> Tuple[List[Hero], bytes]:
    heroes: List[Hero] = []
    i = 0
    n = len(tail)
    for _ in range(max_heroes):
        name, i2 = take_cstring_ascii(tail, i)
        if not name:
            break
        if i2 + 4 > n:
            break
        hero_type = int.from_bytes(tail[i2:i2+4], "little")
        j = i2 + 4
        image, j2 = take_cstring_ascii(tail, j)
        if not image.endswith('.png'):
            break
        need = 16 * 2
        if j2 + need > n:
            break
        stats = [int.from_bytes(tail[k:k+2], "little") for k in range(j2, j2 + need, 2)]
        heroes.append(Hero(name=name, type=hero_type, image=image, stats16=stats))
        i = j2 + need
    return heroes, tail[i:]


def split_citations_ascii_nulls(buf: bytes) -> List[str]:
    parts = [p for p in buf.split(b"\x00") if p]
    out: List[str] = []
    for p in parts:
        try:
            s = p.decode("ascii")
        except Exception:
            s = p.decode("ascii", errors="ignore")
        s = s.strip()
        if s:
            out.append(s)
    return out

# ------------------ décodage histoire ------------------

def decode_history(hist: bytes, mode: str = "auto", limit: int = 200) -> str:
    """Retourne un extrait lisible de l'histoire, sans jamais dépasser la première sentinelle (déjà gérée plus haut).
    - auto : essaie UTF-16LE si la majorité des paires sont <char>,00 ; sinon ASCII.
    - ascii : decode('ascii', errors='ignore')
    - utf16 : decode('utf-16le', errors='ignore')
    """
    s = ""
    if mode == "ascii":
        s = hist.decode('ascii', errors='ignore')
    elif mode == "utf16":
        s = hist.decode('utf-16le', errors='ignore')
    else:  # auto
        even = len(hist) // 2 * 2
        zero_hi_pairs = 0
        for i in range(0, even, 2):
            if hist[i+1] == 0x00:
                zero_hi_pairs += 1
        ratio = zero_hi_pairs / (even//2) if even else 0.0
        if ratio > 0.6:  # heuristique : plutôt UTF-16LE sur base ASCII
            s = hist.decode('utf-16le', errors='ignore')
        else:
            s = hist.decode('ascii', errors='ignore')
    s = s.replace('\r', ' ').replace('\n', ' ').strip()
    return s[:limit]

# ------------------ parse unité complète ------------------

def parse_one_unit(data: bytes, off: int,
                   after_name_window: int = MAX_AFTER_NAME_TO_SENT16,
                   history_window: int = MAX_HISTORY_TO_SENT04,
                   tail_window: int = MAX_TAIL_TO_SENT08,
                   min_run: int = MIN_FF_RUN,
                   max_run: int | None = MAX_FF_RUN) -> Tuple[Unit, int]:
    # 1) Nom
    name, p = read_utf16le_cstr(data, off)

    # 2) 1ère run FF (arrêt STRICTEMENT à la première)
    pos1, len1 = find_next_ff_run(data, p, after_name_window, min_run=min_run, max_run=max_run)
    if pos1 < 0:
        raise ValueError("first FF-run (>=4) not found within bounds after name")
    hist_start = pos1 + len1

    # 3) 2ème run FF (fin de l'histoire)
    pos2, len2 = find_next_ff_run(data, hist_start, history_window, min_run=min_run, max_run=max_run)
    if pos2 < 0:
        raise ValueError("second FF-run (>=4) not found after history within bounds")
    history = data[hist_start:pos2]
    tail_start = pos2 + len2

    # 4) 3ème run FF (fin bloc héros+citations)
    pos3, len3 = find_next_ff_run(data, tail_start, tail_window, min_run=min_run, max_run=max_run)
    if pos3 < 0:
        raise ValueError("third FF-run (>=4) not found after tail within bounds")
    tail = data[tail_start:pos3]

    heroes, rest = parse_heroes_from_tail(tail)
    citations = split_citations_ascii_nulls(rest) if rest else []

    unit = Unit(
        name=name,
        history=history,
        heroes=heroes,
        citations=citations,
        raw_tail_bytes=tail,
        start_off=off,
        end_off=pos3 + len3,
    )
    return unit, unit.end_off

# ------------------ scan ------------------

def scan_units(data: bytes, start_off: int, max_units: int = 1000,
               after_name_window: int = MAX_AFTER_NAME_TO_SENT16,
               history_window: int = MAX_HISTORY_TO_SENT04,
               tail_window: int = MAX_TAIL_TO_SENT08,
               min_run: int = MIN_FF_RUN,
               max_run: int | None = MAX_FF_RUN) -> List[Unit]:
    units: List[Unit] = []
    off = start_off
    for _ in range(max_units):
        if off >= len(data):
            break
        try:
            u, off_next = parse_one_unit(
                data, off,
                after_name_window=after_name_window,
                history_window=history_window,
                tail_window=tail_window,
                min_run=min_run,
                max_run=max_run,
            )
            units.append(u)
            off = off_next
        except ValueError:
            break
    return units

# ------------------ probe (debug) ------------------

def probe_offset(data: bytes, off: int,
                 after_name_window: int = MAX_AFTER_NAME_TO_SENT16,
                 history_window: int = MAX_HISTORY_TO_SENT04,
                 tail_window: int = MAX_TAIL_TO_SENT08,
                 min_run: int = MIN_FF_RUN,
                 max_run: int | None = MAX_FF_RUN) -> dict:
    diag = {
        "offset": off,
        "name": None,
        "name_end": None,
        "run1_pos": None, "run1_len": None,
        "run2_pos": None, "run2_len": None,
        "run3_pos": None, "run3_len": None,
    }
    try:
        name, term_end = read_utf16le_cstr(data, off)
        diag["name"], diag["name_end"] = name, term_end
    except Exception as e:
        diag["error"] = f"name read error: {e}"
        return diag

    pos1, len1 = find_next_ff_run(data, term_end, after_name_window, min_run=min_run, max_run=max_run)
    if pos1 >= 0:
        diag["run1_pos"], diag["run1_len"] = pos1, len1
        hist_start = pos1 + len1
        pos2, len2 = find_next_ff_run(data, hist_start, history_window, min_run=min_run, max_run=max_run)
        if pos2 >= 0:
            diag["run2_pos"], diag["run2_len"] = pos2, len2
            tail_start = pos2 + len2
            pos3, len3 = find_next_ff_run(data, tail_start, tail_window, min_run=min_run, max_run=max_run)
            if pos3 >= 0:
                diag["run3_pos"], diag["run3_len"] = pos3, len3
    return diag

# ------------------ CLI ------------------

def main():
    ap = argparse.ArgumentParser(description="Robust unit scanner (with debug)")
    ap.add_argument("--save", required=True, help="Path to save file")
    ap.add_argument("--units-offset", required=True, help="Offset of 1st unit (hex 0x... or decimal)")
    ap.add_argument("--name", help="Filter: exact unit name (UTF-16LE decoded)")
    ap.add_argument("--list", type=int, default=0, help="List first N units")

    # Debug & affichage
    ap.add_argument("--debug", action="store_true", help="Hexdump + FF-run probe (variable length 4..16) and exit")
    ap.add_argument("--dump", type=int, default=200, help="Bytes to dump after offset in --debug mode (default 200)")
    ap.add_argument("--hist-snippet", type=int, default=120, help="Chars of history preview to print")
    ap.add_argument("--hist-encoding", choices=["auto", "ascii", "utf16"], default="auto", help="History decoding for preview")

    # Fenêtres & runs (override)
    ap.add_argument("--after-name", type=int, default=MAX_AFTER_NAME_TO_SENT16, help="Window after name to look for 1st FF run")
    ap.add_argument("--history", type=int, default=MAX_HISTORY_TO_SENT04, help="Window for history before 2nd FF run")
    ap.add_argument("--tail", type=int, default=MAX_TAIL_TO_SENT08, help="Window for tail before 3rd FF run")
    ap.add_argument("--min-run", type=int, default=MIN_FF_RUN, help="Min FF run length")
    ap.add_argument("--max-run", type=int, default=MAX_FF_RUN, help="Max FF run length (<=16)")

    args = ap.parse_args()

    with open(args.save, "rb") as f:
        data = f.read()

    off = int(args.units_offset, 16) if args.units_offset.lower().startswith("0x") else int(args.units_offset)
    print(f"[start] offset: 0x{off:x} ({off})")

    if args.debug:
        print("\n[hexdump]")
        print(hexdump_slice(data, off, length=args.dump))
        print("\n[probe]")
        d = probe_offset(data, off,
                         after_name_window=args.after_name,
                         history_window=args.history,
                         tail_window=args.tail,
                         min_run=args.min_run,
                         max_run=args.max_run)
        name_end = d.get('name_end') or off
        print(f"name     : {d.get('name')}")
        print(f"name_end : 0x{name_end:x}")
        # Liste des premières runs visibles après le nom (avec distances)
        runs_preview = list_ff_runs(data, name_end, lookahead=args.after_name, min_run=args.min_run, max_run=args.max_run, limit=10)
        if runs_preview:
            print("runs after name (first 10 within window):")
            for pos, len_ in runs_preview:
                print(f"  - at 0x{pos:x}, len={len_}, dist_from_name_end={pos - name_end}")
        else:
            print("runs after name: NONE within window")
        # Trois runs successives avec distances + extrait d'histoire
        pos1, len1 = find_next_ff_run(data, name_end, args.after_name, args.min_run, args.max_run)
        if pos1 >= 0:
            print(f"FF-run #1  : at 0x{pos1:x}, len={len1}, dist_from_name_end={pos1 - name_end}")
            hist_start = pos1 + len1
            pos2, len2 = find_next_ff_run(data, hist_start, args.history, args.min_run, args.max_run)
            if pos2 >= 0:
                print(f"FF-run #2  : at 0x{pos2:x}, len={len2}, dist_from_hist_start={pos2 - hist_start}")
                # aperçu d'histoire (on s'arrête à la première sentinelle)
                hist_bytes = data[hist_start:pos2]
                preview = decode_history(hist_bytes, mode=args.hist_encoding, limit=args.hist_snippet)
                print(f"history preview: {preview!r}")
                tail_start = pos2 + len2
                pos3, len3 = find_next_ff_run(data, tail_start, args.tail, args.min_run, args.max_run)
                if pos3 >= 0:
                    print(f"FF-run #3  : at 0x{pos3:x}, len={len3}, dist_from_tail_start={pos3 - tail_start}")
                else:
                    print("FF-run #3  : NOT FOUND within tail window")
            else:
                print("FF-run #2  : NOT FOUND within history window")
        else:
            print("FF-run #1  : NOT FOUND within after-name window")
        return

    # Scan normal
    units = scan_units(
        data, off,
        after_name_window=args.after_name,
        history_window=args.history,
        tail_window=args.tail,
        min_run=args.min_run,
        max_run=args.max_run,
    )
    print(f"[scan] parsed units: {len(units)}")

    if args.name:
        hits = [u for u in units if u.name == args.name]
        if not hits:
            print(f"No unit named '{args.name}' found")
            return
        for u in hits:
            print(f"=== {u.name} === @ 0x{u.start_off:x}")
            print(f"History: {len(u.history)} bytes  | preview: {decode_history(u.history, args.hist_encoding, args.hist_snippet)!r}")
            print(f"Heroes : {len(u.heroes)}  | Citations: {len(u.citations)}")
            for i, h in enumerate(u.heroes, 1):
                print(f"  [{i}] name={h.name} type={h.type} image={h.image} stats16={h.stats16}")
            if u.citations:
                print("Citations:")
                for i, s in enumerate(u.citations, 1):
                    print(f"  - ({i}) {s}")
    elif args.list:
        for u in units[:args.list]:
            print(f"- {u.name}  @0x{u.start_off:x}  hist={len(u.history)}B  heroes={len(u.heroes)}  quotes={len(u.citations)}  preview={decode_history(u.history, args.hist_encoding, 60)!r}")

if __name__ == "__main__":
    main()
