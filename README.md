# Panzer Corps – Save Decoder Starter Kit

Voici maintenant une **arborescence de projet complète** pour travailler proprement avec Python, un environnement virtuel, et Kaitai Struct.

---

## Arborescence
```
panzercorps-save/
├── explore_save.py          # Script d'exploration initial
├── panzer_corps_save.ksy    # Squelette Kaitai Struct
├── requirements.txt         # Dépendances Python
├── README.md                # Notes et mode d'emploi
├── Makefile                 # Raccourcis utiles (optionnel)
├── .gitignore               # Pour versionner proprement
└── kaitai/
    └── panzer_corps_save.py # (généré par kaitai-struct-compiler)
```

---

## Contenu des fichiers

### `requirements.txt`
```
construct>=2.10
hexdump
```
*(Ajoutez `kaitaistruct` si vous voulez utiliser les bindings Python générés.)*

### `README.md`
```markdown
# Panzer Corps Save Decoder

## Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\\Scripts\\activate   # Windows
pip install -r requirements.txt
```

## Usage
```bash
python explore_save.py saves/MaPartie.sav
```

## Kaitai Struct
- Installez [Kaitai Struct Compiler](https://kaitai.io).
- Compilez le `.ksy` en Python :
```bash
kaitai-struct-compiler -t python panzer_corps_save.ksy -d kaitai/
```

Cela génère `kaitai/panzer_corps_save.py` que vous pouvez importer dans vos scripts.
```

### `Makefile`
```make
venv:
	python -m venv .venv
	. .venv/bin/activate; pip install -r requirements.txt

run:
	. .venv/bin/activate; python explore_save.py sample.sav

kaitai:
	kaitai-struct-compiler -t python panzer_corps_save.ksy -d kaitai/
```

### `.gitignore`
```
.venv/
__pycache__/
*.pyc
*.pyo
*.log
.DS_Store
kaitai/*.py
```

---

## Étapes suivantes
- Créez un répertoire `saves/` pour stocker vos fichiers de test A/B/C.
- Lancez `make kaitai` après chaque modification du `.ksy`.
- Enrichissez progressivement le parseur avec vos découvertes.

Ainsi vous avez une base de projet bien structurée, facile à versionner et à partager.

