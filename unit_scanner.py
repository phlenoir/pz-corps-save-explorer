#!/usr/bin/env python3
"""
Robust unit scanner.

Features:
- Detects sentinels as **runs of 0xFF** (length >= min_run, default 4).
- Stops **strictly at the first sentinel** found after each block.
- `--debug` mode: hexdump, run overview, distances, readable history snippet.

Usage:
    python unit_scanner.py --save saves/example.sav --units-offset 0x39EA9 --debug --dump 200
    python unit_scanner.py --save saves/example.sav --units-offset 0x39EA9 --list 5
    python unit_scanner.py --save saves/example.sav --units-offset 0x39EA9 --name "45th SdKfz  7/2"
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

# ------------------ constantes ------------------
MIN_FF_RUN = 4
MAX_FF_RUN = 16

# Fenêtres par défaut (surchargeables par CLI)
MAX_AFTER_NAME_TO_SENT = 4096      # octets max entre fin du nom et 1ère sentinelle
MAX_HISTORY_TO_SENT    = 256_000   # taille max de l'histoire
MAX_TAIL_TO_SENT       = 512_000   # taille max du bloc héros+citations
MAX_HEROES             = 3

# ------------------ dataclasses ------------------
@dataclass
class Hero:
    name: str
    image: str
    stats16: List[int]
    stats16_off: Optional[int] = None  # offset dans le fichier (si connu)

@dataclass
class Unit:
    name: str
    stats: List[int]
    stats_off: int
    history: bytes
    heroes: List[Hero]
    citations: List[str]
    raw_tail_bytes: bytes
    start_off: int
    end_off: int
    idx: Optional[int] = None   # index dans la liste scannée (1-based)

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

UNIT_STAT_INDEX: Dict[str, int] = {
    "strength"   : 5,
    "max_strength": 7,
    "xp"         : 13,
    "fuel"       : 21,
    "ammo"       : 23,
    "kills"      : 28,
    "losses"     : 30,
    "kill_inf"  : 32,
    "kill_tank" : 34,
    "kill_reco" : 36,
    "kill_at"   : 38,
    "kill_art"  : 40,
    "kill_aa"   : 42,
    "kill_bunker": 44,
    "kill_fighter": 46,
    "kill_tbomber": 48,
    "kill_sbomber": 50,
    "kill_submarine": 52,
    "kill_destroyer": 54,
    "kill_cruiser": 56,
    "kill_carrier": 58,
    "kill_truck": 60,
    "kill_airtransport": 62,
    "kill_seatransport": 64,
    "kill_train": 66,
}

# ------------------ helpers encodage ------------------

def read_utf16le_cstr(data: bytes, off: int) -> tuple[str, int]:
    """
    Lit une C-string UTF-16LE terminée par 0x00 0x00 à partir de `off`.
    Accepte les caractères accentués (plein UTF-16LE).
    Retourne (texte, nouvel_offset_après_terminateur).
    """
    n = len(data)
    i = off
    buf = bytearray()

    while True:
        if i + 1 >= n:
            raise ValueError("EOF while reading UTF-16LE string")
        lo = data[i]
        hi = data[i + 1]
        i += 2
        if lo == 0x00 and hi == 0x00:
            # fin de chaîne
            break
        buf.append(lo)
        buf.append(hi)

    try:
        s = buf.decode("utf-16le")          # plein UTF-16 (accents, etc.)
    except UnicodeDecodeError:
        s = buf.decode("utf-16le", errors="replace")  # sécurité si données corrompues

    return s, i


def is_printable_ascii(b: int) -> bool:
    return 32 <= b < 127

def skip_leading_non_ascii(buf: bytes, start: int, max_skip: int = 256) -> int:
    """
    Avance tant que les octets ne sont PAS imprimables ASCII.
    Limite la recherche à max_skip octets pour éviter de balayer la moitié du fichier.
    Retourne le nouvel index (>= start).
    """
    n = len(buf)
    i = start
    end = min(n, start + max_skip)
    while i < end and not is_printable_ascii(buf[i]):
        i += 1
    return i

def bytes_to_u16_list(data: bytes, length: Optional[int] = None) -> List[int]:
    """
    Convertit un tableau de bytes en liste d'entiers non signés sur 2 octets (little-endian).
    - data : tableau de bytes source
    - length : nombre d'octets à analyser (par défaut = toute la longueur)
    
    Si la longueur (réelle ou fournie) est impaire, l'octet final est ignoré.
    """
    if length is None or length > len(data):
        length = len(data)
    n = length // 2 * 2  # arrondir à l'entier pair inférieur
    out = []
    for i in range(0, n, 2):
        val = int.from_bytes(data[i:i+2], "little")
        out.append(val)
    return out

# ------------------ recherches sentinelles ------------------

def find_next_ff_run(data: bytes, start: int, max_advance: int,
                     min_count: int = MIN_FF_RUN, max_run: Optional[int] = MAX_FF_RUN) -> tuple[int, int]:
    """
    Trouve la première **suite contiguë** de 0xFF à partir de `start` dans la fenêtre `max_advance`.
    Renvoie (pos_debut_run, nb_FF_dans_la_run) ou (-1, 0) si non trouvée.
    """
    end = min(len(data), start + max_advance)
    i = start
    while i < end:
        try:
            i = data.index(0xFF, i, end)
        except ValueError:
            return -1, 0
        j = i
        while j < end and data[j] == 0xFF and (max_run is None or (j - i) < max_run):
            j += 1
        run_len = j - i
        if run_len >= min_count:
            return i, run_len
        i = j
    return -1, 0

def list_ff_runs(data: bytes, start: int, lookahead: int,
                 min_count: int = MIN_FF_RUN, max_run: Optional[int] = MAX_FF_RUN,
                 limit: int = 10) -> list[tuple[int,int]]:
    out = []
    end = min(len(data), start + lookahead)
    i = start
    while i < end and len(out) < limit:
        pos, cnt = find_next_ff_run(data, i, end - i, min_count=min_count, max_run=max_run)
        if pos < 0:
            break
        out.append((pos, cnt))
        i = pos + cnt  # IMPORTANT: on saute toute la run contiguë
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

# ------------------ parsing heroes & citations ------------------

def looks_non_ascii_block(b: bytes) -> bool:
    """Heuristique: 'non-ascii' si >75% des octets ne sont pas imprimables ASCII."""
    if not b:
        return False
    non_print = sum(1 for x in b if not (32 <= x < 127))
    return non_print / len(b) >= 0.75

def parse_one_hero(
    data: bytes, 
    off: int,
    min_run: int = 4,
    max_run: int | None = 16,
    run_search_window: int = 64_000,
    ) -> tuple[Hero | None, int]:
    """
    Parse un héros à partir de off :
      - (padding non-ASCII éventuel)
      - name : C-ASCII
      - (padding non-ASCII éventuel)
      - image : C-ASCII qui finit par .png
      - stats : 16 * u16 little-endian
    Retourne (Hero|None, new_off). None si non plausible/incomplet.
    """
    #print("\n[hero]")
    #print(hexdump_slice(data, off))
    n = len(data)

    # name
    name, i = read_utf16le_cstr(data, off)
    j = i + 4
    if not name or j > n:
        return None, off
    #print(f"  Found {name}")

    # image (C-ASCII)
    image, k = read_utf16le_cstr(data, j)
    if not image.endswith(".png"):
        return None, off
    #print(f"  image {image}")

    # Chaque héros doit être suivi d'une sentinelle contiguë de 0xFF
    pos, runlen = find_next_ff_run(
        data,
        start=k,
        max_advance=min(run_search_window, n - k),
        min_count=min_run,
        max_run=max_run,
    )
    if pos < 0:
        # pas de sentinelle -> on s'arrête
        return None, off
        
    # 16 * u16
    need = 16 * 2
    stats16_off = pos + runlen
    stats16_end = stats16_off + need
    if stats16_off + need > n:
        return None, off
    stats16 = [int.from_bytes(data[l:l+2], "little") for l in range(stats16_off, stats16_end, 2)]
    #print(f"  stats16 {stats16}")

    return Hero(name=name, image=image, stats16=stats16, stats16_off=stats16_off), stats16_end + 2


def parse_heroes_with_sentinels(
    data: bytes,
    after_sentinel_off: int,
    min_run: int = 4,
    max_run: int | None = 16,
    max_heroes_cap: int = MAX_HEROES,
    run_search_window: int = 64_000,
) -> tuple[list[Hero], int, int, int]:
    """
    Lit le compteur de héros (1 octet) à `after_sentinel_off`, puis lit EXACTEMENT
    ce nombre de héros, chaque héros étant suivi d'une **sentinelle** (suite contiguë de 0xFF).

    Retourne (heroes, nb_declares, nb_lus, new_off) où:
      - heroes: liste de Hero parsés
      - nb_declares: valeur du compteur trouvé (0..255)
      - nb_lus: nombre réellement parsé (capé par max_heroes_cap)
      - new_off: position juste après la sentinelle suivant le DERNIER héros (ou au point d'arrêt)
    """
    n = len(data)
    i = after_sentinel_off
    if i >= n:
        return [], 0, 0, i

    nb_declares = data[i]
    i += 8

    # Cap (si format connu 0..3)
    target = min(nb_declares, max_heroes_cap)
    #print(f"\nScanning for {target} heroes")

    heroes: list[Hero] = []
    for _ in range(target):
        hero, next_i = parse_one_hero(data, i)
        if hero is None:
            # format inattendu -> on s'arrête proprement
            return heroes, nb_declares, len(heroes), i

        heroes.append(hero)
        i = next_i

    # i pointe après les stats du dernier héros
    return heroes, nb_declares, len(heroes), i


def split_citations_ascii16(buf: bytes) -> list[str]:
    """
    Lit des citations encodées 'ASCII sur 2 octets' (UTF-16LE appauvri) :
      - caractère = (lo, 0x00) avec 32 <= lo < 127
      - séparateur = (0x00, 0x00) ; plusieurs séparateurs à la suite sont fusionnés
    Essaie les deux alignements (0 ou 1) et choisit celui qui donne le plus d'ASCII.
    """
    def parse(start: int) -> list[str]:
        out, cur = [], []
        i, n = start, len(buf)
        # on ne lit que des paires complètes
        while i + 1 < n:
            lo, hi = buf[i], buf[i+1]
            i += 2
            if lo == 0x00 and hi == 0x00:
                s = "".join(cur).strip()
                if s:
                    out.append(s)
                cur = []
                # sauter séparateurs (00 00) répétés
                while i + 1 < n and buf[i] == 0x00 and buf[i+1] == 0x00:
                    i += 2
                continue
            if hi == 0x00 and 32 <= lo < 127:
                cur.append(chr(lo))
            # sinon: on ignore (padding / bruit / non-ASCII)
        # flush final
        s = "".join(cur).strip()
        if s:
            out.append(s)
        return out

    a0 = parse(0)
    a1 = parse(1)
    # score simple: quantité d'ASCII utile produite
    score0 = sum(len(s) for s in a0)
    score1 = sum(len(s) for s in a1)
    return a0 if score0 >= score1 else a1


# ------------------ décodage ------------------

def utf16_ascii_from_bytes(b: bytes) -> str:
    """Interprète b comme une suite de paires (lo,hi) et ne garde que les
    caractères dont hi==0x00 et 32<=lo<127. Utile pour éviter les CJK fantômes."""
    out = []
    n = len(b) // 2 * 2
    for i in range(0, n, 2):
        lo = b[i]
        hi = b[i+1]
        if hi == 0x00 and 32 <= lo < 127:
            out.append(chr(lo))
    return ''.join(out)

def decode_history(hist_bytes: bytes, offset: int = 185, snippet: int = 160) -> str:
    """Construit l'aperçu d'histoire 
    """
    h = hist_bytes[offset:]
    s = utf16_ascii_from_bytes(h)
    return s[:snippet]    

# ------------------ parse unité complète ------------------

def parse_one_unit(data: bytes, off: int, hist_head_off: int,
                   after_name_window: int = MAX_AFTER_NAME_TO_SENT,
                   history_window: int = MAX_HISTORY_TO_SENT,
                   tail_window: int = MAX_TAIL_TO_SENT,
                   min_run: int = MIN_FF_RUN,
                   max_run: Optional[int] = MAX_FF_RUN) -> Tuple[Unit, int]:
    
    # Make sure we start on a readable caracter
    first_readable = skip_leading_non_ascii(data, off)
    name, p = read_utf16le_cstr(data, first_readable)

    # 1) 1ère sentinelle après le nom
    pos1, cnt1 = find_next_ff_run(data, p, after_name_window, min_count=min_run, max_run=max_run)
    if pos1 < 0:
        raise ValueError("first FF-run (>=min_run) not found within bounds after name")
    hist_start = pos1 + (cnt1 if max_run is None else min(cnt1, max_run))
    stats_off = hist_start + 1  # should be the first byte of stats (u16[66])
    hist_head = data[stats_off:]
    stats = bytes_to_u16_list(hist_head, hist_head_off)

    # 2) 2ème sentinelle (fin histoire) 
    pos2, cnt2 = find_next_ff_run(data, hist_start, history_window, min_count=min_run, max_run=max_run)
    if pos2 < 0:
        raise ValueError("no history boundary found (neither FF-run nor hero start)")
    history = data[hist_start:pos2]
    
    heroes_start = pos2 + cnt2   # the 1st of next bytes is the number of heroes

    heroes, nb_declares, nb_lus, after_heroes_off = parse_heroes_with_sentinels(
        data,
        after_sentinel_off=heroes_start,
        min_run=min_run,
        max_run=max_run,
        max_heroes_cap=MAX_HEROES,
    )

    # 3) dernière sentinelle (fin unité)
    pos3, cnt3 = find_next_ff_run(data, after_heroes_off, tail_window, min_count=min_run, max_run=max_run)
    if pos3 < 0:
        raise ValueError("third FF-run (>=min_run) not found after heroes within bounds")

    tail = data[after_heroes_off:pos3]
    citations = split_citations_ascii16(tail) if after_heroes_off else []

    unit = Unit(
        name=name,
        stats=stats,
        stats_off=stats_off if stats else None,
        history=history,
        heroes=heroes,
        citations=citations,
        raw_tail_bytes=tail,
        start_off=off,
        end_off=pos3 + cnt3 + 4, # there is a minimum of 4 bytes to the next unit
    )
    return unit, unit.end_off

# ------------------ scan ------------------

def scan_units(data: bytes, start_off: int, hist_head_off: int = 185, max_units: int = 100,
               after_name_window: int = MAX_AFTER_NAME_TO_SENT,
               history_window: int = MAX_HISTORY_TO_SENT,
               tail_window: int = MAX_TAIL_TO_SENT,
               min_run: int = MIN_FF_RUN,
               max_run: Optional[int] = MAX_FF_RUN) -> List[Unit]:
    units: List[Unit] = []
    off = start_off
    idx = 1
    for _ in range(max_units):
        if off >= len(data):
            break
        try:
            u, off_next = parse_one_unit(
                data, off, hist_head_off=hist_head_off,
                after_name_window=after_name_window,
                history_window=history_window,
                tail_window=tail_window,
                min_run=min_run,
                max_run=max_run,
            )
            u.idx = idx
            units.append(u)
            off = off_next
            idx += 1
        except ValueError:
            print("\n[ValueError]")
            print(hexdump_slice(data, off))
            break
    print(f"[scan_units] parsed {len(units)} units")
    return units

# ------------------ probe (debug) ------------------

def probe_offset(data: bytes, off: int, hist_head_off: int,
                 after_name_window: int = MAX_AFTER_NAME_TO_SENT,
                 history_window: int = MAX_HISTORY_TO_SENT,
                 tail_window: int = MAX_TAIL_TO_SENT,
                 min_run: int = MIN_FF_RUN,
                 max_run: Optional[int] = MAX_FF_RUN) -> dict:
    diag = {"offset": off}
    try:
        name, term_end = read_utf16le_cstr(data, off)
        diag.update({"name": name, "name_end": term_end})
    except Exception as e:
        diag.update({"error": f"name read error: {e}"})
        return diag

    # Runs après le nom
    runs_after = list_ff_runs(data, term_end, after_name_window, min_count=min_run, max_run=max_run, limit=10)
    diag["runs_after_name"] = runs_after

    # Première run
    pos1, cnt1 = find_next_ff_run(data, term_end, after_name_window, min_count=min_run, max_run=max_run)
    diag["run1"] = (pos1, cnt1)

    # Deuxième run (ou héros)
    if pos1 >= 0:
        hist_start = pos1 + (cnt1 if max_run is None else min(cnt1, max_run))
        pos2, cnt2 = find_next_ff_run(data, hist_start, history_window, min_count=min_run, max_run=max_run)
        if pos2 >= 0:
            diag["run2"] = (pos2, cnt2)
        else:
            heroe_cnt = data[pos2 + cnt2]   # the next byte is the number of heroes
            if heroe_cnt > 0:
                diag["hero_start"] = pos2 + cnt2 + 8
        # Troisième run
        tstart = (pos2 + cnt2 + 8) 
        if tstart is not None:
            pos3, cnt3 = find_next_ff_run(data, tstart, tail_window, min_count=min_run, max_run=max_run)
            diag["run3"] = (pos3, cnt3)
    return diag

# ------------------ CLI ------------------

def main():
    ap = argparse.ArgumentParser(description="Robust unit scanner (with debug, contiguous FF-runs)")
    ap.add_argument("--save", required=True, help="Path to save file")
    ap.add_argument("--units-offset", required=True, help="Offset of 1st unit (hex 0x... or decimal)")
    ap.add_argument("--name", help="Filter: exact unit name (UTF-16LE decoded)")
    ap.add_argument("--list", type=int, default=0, help="List first N units")

    # Debug & affichage
    ap.add_argument("--debug", action="store_true", help="Hexdump + FF-run probe (variable length, gaps) and exit")
    ap.add_argument("--dump", type=int, default=200, help="Bytes to dump after offset in --debug mode (default 200)")
    ap.add_argument("--hist-snippet", type=int, default=160, help="Chars of history preview (default 160)")
    ap.add_argument("--hist-offset", type=int, default=132, help="Byte offset into history to collect stats")
    # Fenêtres & runs (override)
    ap.add_argument("--after-name", type=int, default=MAX_AFTER_NAME_TO_SENT, help="Window after name to look for 1st boundary")
    ap.add_argument("--history", type=int, default=MAX_HISTORY_TO_SENT, help="Window for history before 2nd boundary")
    ap.add_argument("--tail", type=int, default=MAX_TAIL_TO_SENT, help="Window for tail before 3rd boundary")
    ap.add_argument("--min-run", type=int, default=MIN_FF_RUN, help="Min number of 0xFF in a run")
    ap.add_argument("--max-run", type=int, default=MAX_FF_RUN, help="Max total run length (<=16) or set big if unsure")

    args = ap.parse_args()

    with open(args.save, "rb") as f:
        data = f.read()

    off = int(args.units_offset, 16) if args.units_offset.lower().startswith("0x") else int(args.units_offset)
    print(f"[start] offset: 0x{off:x} ({off})")

    if args.debug:
        print("\n[hexdump]")
        print(hexdump_slice(data, off, length=args.dump))
        print("\n[probe]")
        d = probe_offset(data, off, hist_head_off=args.hist_offset,
                         after_name_window=args.after_name,
                         history_window=args.history,
                         tail_window=args.tail,
                         min_run=args.min_run,
                         max_run=args.max_run)
        name = d.get('name'); name_end = d.get('name_end') or off
        print(f"name       : {name}")
        print(f"name_end   : 0x{name_end:x}")
        runs = d.get('runs_after_name') or []
        if runs:
            print("runs after name (within window):")
            for pos, cnt in runs:
                print(f"  - at 0x{pos:x}, FF_count={cnt}, dist={pos - name_end}")
        r1 = d.get('run1'); r2 = d.get('run2'); r3 = d.get('run3'); hero = d.get('hero_start')
        if r1:
            print(f"boundary #1: FF-run at 0x{r1[0]:x}, FF_count={r1[1]}, dist_from_name_end={r1[0]-name_end}")
            hist_start = r1[0] + r1[1]
            if r2:
                print(f"boundary #2: FF-run at 0x{r2[0]:x}, FF_count={r2[1]}, dist_from_hist_start={r2[0]-hist_start}")
                tstart = r2[0] + r2[1]
            elif hero and hero > 0:
                print(f"boundary #2: HERO-FALLBACK at 0x{hero:x}, dist_from_hist_start={hero - hist_start}")
                tstart = hero
            else:
                print("boundary #2: NOT FOUND")
                tstart = None
            if tstart is not None and r3 and r3[0] >= 0:
                print(f"boundary #3: FF-run at 0x{r3[0]:x}, FF_count={r3[1]}, dist_from_tail_start={r3[0]-tstart}")
            elif tstart is not None:
                print("boundary #3: NOT FOUND within tail window")
        else:
            print("boundary #1: NOT FOUND within after-name window")
        return

    # Scan normal
    units = scan_units(
        data, off, hist_head_off=args.hist_offset,
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
            print(f"Stats:stats={h.stats}")
            print(f"History: {len(u.history)} bytes  | preview: {decode_history(u.history, args.hist_offset, args.hist_snippet)!r}")
            print(f"Heroes : {len(u.heroes)}  | Citations: {len(u.citations)}")
            for i, h in enumerate(u.heroes, 1):
                print(f"  [{i}] name={h.name} type={h.type} image={h.image} stats16={h.stats16}")
            if u.citations:
                print("Citations:")
                for i, s in enumerate(u.citations, 1):
                    print(f"  - ({i}) {s}")
    elif args.list:
        for u in units[:args.list]:
            print(f"- {u.name}  @0x{u.start_off:x}  hist={len(u.history)}B  heroes={len(u.heroes)}  quotes={len(u.citations)}  preview={decode_history(u.history, args.hist_offset, 60)!r}")

if __name__ == "__main__":
    main()
