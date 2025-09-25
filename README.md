# Panzer Corps – Save Decoder Starter Kit

Here is the **project structure** - works with Python and a virtual environment.

---
## Project Structure

```
pz-corps-save-explorer/
├── requirements.txt         # Python dependencies
├── README.md                # Documentation and usage instructions
├── .gitignore               # Git ignore rules
├── saves/                   # Directory for test save files
├── unit_scanner.py          # Main parser 
├── show_unit.py             # Use scanner to display ONE or MANY units
├── stats_editor.py          # Use scanner to update unit or hero stats
├── find_unit_offsets.py     # Search all occurence of an ascii text in a .pzsav file
└── .venv/                   # Python virtual environment (not tracked by git)
```

---

## Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\\Scripts\\activate   # Windows
. .venv/Scripts/activate   # git bash on Windows
pip install -r requirements.txt
```

## Usage

### 1. Scan a Save File

Use `unit_scanner.py` to parse a save file and list units:

```bash
  python unit_scanner.py --save saves/Kiev43.pzsav --units-offset 0x07CA48 --debug --dump 200
  python unit_scanner.py --save saves/Kiev43.pzsav --units-offset 0x07CA48 --list 5
  python unit_scanner.py --save saves/Kiev43.pzsav --units-offset 0x07CA48 --name "45th SdKfz  7/2"
```

### 2. Display Specific Units

Use `show_unit.py` to display information about one or more units:

```bash

# Search by unit name
python show_unit.py saves/Kiev43.pzsav "45th SdKfz  7/2" --units-offset 0x07CA48

# Directly by Offset (first unit at this offset)
python show_unit.py --units-offset 0x07CA48 saves/Kiev43.pzsav

# By offset + index (e.g., 2nd unit from the offset)
python show_unit.py saves/Kiev43.pzsav --units-offset 0x07CA48 --index 2

# By offset + multiple units (e.g., 3 units from the offset)
python show_unit.py saves/Kiev43.pzsav --units-offset 0x07CA48 --count 3
```

Refer to each script's `--help` option for more details:

```bash
python unit_scanner.py --help
python show_unit.py --help
```

### 2. Modify Unit or Hero stats

```bash
# Dry-run: change hero stats (first hero) by unit name
python stats_editor.py --save saves/Kiev43.pzsav --units-offset 0x07CA48 \
  --unit-name "45th SdKfz  7/2" --hero-index 1 --set attack=22 movement=8

# Write back (creates .bak)
python stats_editor.py --save saves/Kiev43.pzsav --units-offset 0x07CA48 \
  --unit-name "45th SdKfz  7/2" --hero-index 1 --set attack=22 movement=8 --write

# By unit index instead of name
python stats_editor.py --save saves/Kiev43.pzsav --units-offset 0x07CA48 \
  --unit-index 2 --hero-index 1 --set defense=12 --write
```

## Finding a Unit in a Panzer Corps Save File

The goal is to identify the exact offset of a unit in the `.pzsav` file so that its characteristics can be analyzed with the scanner.

---

## 1. Using the Search Script

Use the `find_unit_offsets.py` script, which scans the whole file for a **name encoded in UTF-16LE**  
(each character stored on 2 bytes, followed by a `00 00` terminator).

### Example
```bash
python find_unit_offsets.py saves/Kiev43.pzsav "45th SdKfz  7/2"
# you may also search for a specific hero and then "manually" search for the unit
python find_unit_offsets.py saves/Kiev43.pzsav "Oleh Dir"
```

To parse units from a Panzer Corps save file, you first need the **offset of the first unit**.  
Here is how to locate it:

1. **Locate the 2nd end of the scenario objective text (red marker)**  
   - At the beginning of the save file you’ll see scenario metadata, including the objectives.  
   - This text is stored as UTF-16LE (every visible character is followed by `00`).  
   - Scroll until you reach the end of this block — this marks the end of the scenario metadata.
   - It seems that this block appears twice in the saved files, together with the unit list, so find the second occurence.


2. **Find the name of the first unit (blue marker)**  
   - Immediately after the 2nd objective block, the 2nd list of units begins.  
   - Each unit name is stored in UTF-16LE and terminated by `00 00`.  
   - Example for *“45th SdKfz  7/2”*:  
     ```
     34 00 35 00 74 00 68 00 20 00 53 00 64 00 4B 00 ...
     ```

3. **Pinpoint the first letter of the unit name (yellow marker)**  
   - Note both the **line start address** and the **column offset** in your hex editor.  
   - In the example screenshot, the line starts at `0x7CA40`.  
   - The first letter of the unit name is at the 9th position on that line → column `8` in hexadecimal.  

4. **Compute the absolute offset**  
   - Add the line base offset (`0x7CA40`) to the column offset (`0x08`):  
     ```
     0x7CA40 + 0x0D = 0x7CA48
     ```
   - This value (`0x7CA48`) is the exact offset of the first unit.

---

### Example Screenshot

![Finding first unit offset](find%201st%20unit%20offset.png)

In this screenshot:
- Red = end of scenario objective text  
- Blue = beginning of the unit name area  
- Yellow = first letter of the unit name (absolute offset = `0x7CA48`)

