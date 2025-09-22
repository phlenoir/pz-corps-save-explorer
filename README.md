# Panzer Corps – Save Decoder Starter Kit

Voici maintenant une **arborescence de projet complète** pour travailler proprement avec Python et un environnement virtuel.

---
## Project Structure

```
pz-corps-save-explorer/
├── requirements.txt         # Python dependencies
├── README.md                # Documentation and usage instructions
├── .gitignore               # Git ignore rules
├── saves/                   # Directory for test save files
├── robust_unit_scanner.py   # Main parser 
├── show_unit.py             # Use scanner to display ONE or MANY units
└── .venv/                   # Python virtual environment (not tracked by git)
```

---

## Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\\Scripts\\activate   # Windows
pip install -r requirements.txt
```

## Usage

### 1. Scan a Save File

Use `robust_unit_scanner.py` to parse a save file and list units:

```bash
  python robust_unit_scanner.py --save saves/exemple.sav --units-offset 0x39ED9 --debug --dump 200
  python robust_unit_scanner.py --save saves/exemple.sav --units-offset 0x39ED9 --list 5
  python robust_unit_scanner.py --save saves/exemple.sav --units-offset 0x39ED9 --name "45th SdKfz  7/2"
```

### 2. Display Specific Units

Use `show_unit.py` to display information about one or more units:

```bash
# Display a single unit by ID
python show_unit.py saves/example_save.dat --unit-id 42

# Display multiple units by IDs
python show_unit.py saves/example_save.dat --unit-id 42 17 8

# Search by unit name
python show_unit.py saves/exemple.sav "45th SdKfz  7/2" --units-offset 0x39ED9

# Directly by Offset (first unit at this offset)
python show_unit.py saves/exemple.sav --units-offset 0x39ED9

# By offset + index (e.g., 2nd unit from the offset)
python show_unit.py saves/exemple.sav --units-offset 0x39ED9 --index 2

# By offset + multiple units (e.g., 3 units from the offset)
python show_unit.py saves/exemple.sav --units-offset 0x39ED9 --count 3
```

Refer to each script's `--help` option for more details:

```bash
python robust_unit_scanner.py --help
python show_unit.py --help
```

## How to find the offset of the first unit in a .pzsav file

## Finding the offset of the first unit in a `.pzsav` file

To parse units from a Panzer Corps save file, you first need the **offset of the first unit**.  
Here is how to locate it:

1. **Locate the end of the scenario objective text (🔴 red marker)**  
   - At the beginning of the save file you’ll see scenario metadata, including the objectives.  
   - This text is stored as UTF-16LE (every visible character is followed by `00`).  
   - Scroll until you reach the end of this block — this marks the end of the scenario metadata.  

2. **Find the name of the first unit (🔵 blue marker)**  
   - Immediately after the objectives, the list of units begins.  
   - Each unit name is stored in UTF-16LE and terminated by `00 00`.  
   - Example for *“45th SdKfz  7/2”*:  
     ```
     34 00 35 00 74 00 68 00 20 00 53 00 64 00 4B 00 ...
     ```

3. **Pinpoint the first letter of the unit name (🟡 yellow marker)**  
   - Note both the **line start address** and the **column offset** in your hex editor.  
   - In the example screenshot, the line starts at `0x39F10`.  
   - The first letter of the unit name is at the 13th character on that line → column `D` in hexadecimal.  

4. **Compute the absolute offset**  
   - Add the line base offset (`0x39F10`) to the column offset (`0x0D`):  
     ```
     0x39F10 + 0x0D = 0x39F1D
     ```
   - This value (`0x39F1D`) is the exact offset of the first unit.

---

### Example Screenshot

![Finding first unit offset](find%201st%20unit%20offset.png)

In this screenshot:
- 🔴 Red = end of scenario objective text  
- 🔵 Blue = beginning of the unit name area  
- 🟡 Yellow = first letter of the unit name (absolute offset = `0x39F1D`)

