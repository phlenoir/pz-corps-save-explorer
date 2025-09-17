#!/usr/bin/env python3
from __future__ import annotations
import argparse
from construct import (
    Struct, Int32ul, Int16ul, Array, Const, CString, Computed,
    RepeatUntil, Adapter, this
)

# ------------------------------
# UTF-16LE C-string (terminée par 0x0000)
# ------------------------------
class Utf16LeCString(Adapter):
    def __init__(self):
        # Lit des u16 jusqu'à rencontrer 0x0000 (inclus)
        super().__init__(RepeatUntil(lambda x, lst, ctx: x == 0, Int16ul))

    def _decode(self, obj, context, path):
        # obj = liste d'entiers u16 (dernier = 0)
        codepoints = obj[:-1] if obj and obj[-1] == 0 else obj
        return ''.join(chr(cp) for cp in codepoints)

    def _encode(self, obj, context, path):
        # Encode str -> liste de u16 + terminator 0
        return [ord(ch) for ch in obj] + [0]

UTF16LE_CString = Utf16LeCString()

# ------------------------------
# Enregistrement unité
# ------------------------------
UnitRecord = Struct(
    "name" / UTF16LE_CString,
    "unit_type" / Int32ul,
    "image_name" / CString("ascii"),
    "sentinel_ff" / Const(b"\xff\xff\xff\xff\xff\xff\xff\xff"),
    "bonuses" / Array(16, Int32ul),
    # Champs dérivés (indices 0-based)
    "attack" / Computed(this.bonuses[3]),      # 4ème
    "defense" / Computed(this.bonuses[5]),     # 6ème
    "initiative" / Computed(this.bonuses[6]),  # 7ème
    "movement" / Computed(this.bonuses[8]),    # 9ème
    "spotting" / Computed(this.bonuses[10]),   # 11ème
    "range" / Computed(this.bonuses[12]),      # 13ème
)

# ------------------------------
# Fichier de sauvegarde minimal (à adapter si header)
# ------------------------------
SaveFile = Struct(
    "unit_count" / Int32ul,
    "units" / Array(this.unit_count, UnitRecord),
)

# ------------------------------
# CLI de démonstration
# ------------------------------
def main():
    ap = argparse.ArgumentParser(description="Parse Panzer Corps save (Construct)")
    ap.add_argument("savefile", help=".sav path")
    args = ap.parse_args()

    with open(args.savefile, "rb") as f:
        data = f.read()

    obj = SaveFile.parse(data)
    print(f"Units: {len(obj.units)}\n" + "-" * 80)
    print(f"{'Name':30}  {'Type':>6}  {'Image':20}  {'Atk':>4} {'Def':>4} {'Init':>4} {'Move':>4} {'Spot':>4} {'Rng':>3}")
    print("-" * 80)
    for u in obj.units:
        print(
            f"{u.name[:30]:30}  {u.unit_type:6}  {u.image_name[:20]:20}  "
            f"{u.attack:4} {u.defense:4} {u.initiative:4} {u.movement:4} {u.spotting:4} {u.range:3}"
        )

    # Exemple de round-trip (reconstruction binaire):
    rebuilt = SaveFile.build(obj)
    assert rebuilt == data, "Round-trip mismatch: ajustez la structure si nécessaire."

if __name__ == "__main__":
    main()
