from dataclasses import dataclass
import struct, zlib, gzip, io, sys, binascii

def try_decompress(buf: bytes) -> bytes:
    # GZIP ?
    if buf.startswith(b"\x1f\x8b"):
        return gzip.decompress(buf)
    # zlib courants
    if buf.startswith((b"\x78\x01", b"\x78\x9c", b"\x78\xda")):
        return zlib.decompress(buf)
    return buf  # pas compressé (ou autre algo)

def hexdump(b: bytes, width=16, limit=512):
    out = []
    for off in range(0, min(len(b), limit), width):
        chunk = b[off:off+width]
        hexpart = " ".join(f"{x:02x}" for x in chunk)
        asciipart = "".join(chr(x) if 32 <= x < 127 else "." for x in chunk)
        out.append(f"{off:08x}  {hexpart:<{width*3}}  |{asciipart}|")
    return "\n".join(out)

def scan_utf16le_strings(b: bytes, min_chars=3):
    s = []
    i = 0
    while i+1 < len(b):
        # séquence UTF-16LE simple (lettre + 0x00)
        start = i
        chars = []
        while i+1 < len(b):
            lo, hi = b[i], b[i+1]
            if hi != 0x00 or lo < 0x20 or lo > 0x7E:
                break
            chars.append(chr(lo))
            i += 2
        if len(chars) >= min_chars:
            s.append((start, "".join(chars)))
        i += 2 if i == start else 0
        i += 2
    return s

@dataclass
class Unit:
    id: int
    x: int
    y: int
    hp: int

def parse_minimal_units(b: bytes, base_offset: int, count: int):
    # EXEMPLE: record hypothétique 9 octets (u32 id, u16 x, u16 y, u8 hp)
    units = []
    off = base_offset
    rec_size = 9
    for _ in range(count):
        (uid,) = struct.unpack_from("<I", b, off); off += 4
        x, y = struct.unpack_from("<HH", b, off); off += 4
        (hp,) = struct.unpack_from("<B", b, off); off += 1
        units.append(Unit(uid, x, y, hp))
    return units

def main(path):
    raw = open(path, "rb").read()
    data = try_decompress(raw)

    print("[*] Raw size:", len(raw), " Decompressed:", len(data))
    print("[*] Head hexdump:\n", hexdump(data, limit=256))

    # Cherche quelques chaînes UTF-16LE (noms d’unités/scénarios)
    utf16 = scan_utf16le_strings(data)
    for off, s in utf16[:10]:
        print(f"[UTF16LE] @{off:#x}: {s}")

    # Heuristique: supposer qu'à l'offset 0x10 on a unit_count (u32)
    try:
        unit_count = struct.unpack_from("<I", data, 0x10)[0]
        print("[?] unit_count candidate:", unit_count)
        # Puis supposer des records à partir de 0x20 …
        units = parse_minimal_units(data, 0x20, min(unit_count, 50))
        print(f"[?] Parsed {len(units)} units (first 3 shown):", units[:3])
    except Exception as e:
        print("[!] Minimal parse failed:", e)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python explore_save.py <savefile>")
        sys.exit(1)
    main(sys.argv[1])
