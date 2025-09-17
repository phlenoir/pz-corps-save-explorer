# Panzer Corps – Save Decoder Starter Kit

Voici maintenant une **arborescence de projet complète** pour travailler proprement avec Python, un environnement virtuel, et Kaitai Struct.

---

## Arborescence
```
panzercorps-save/
├── explore_save.py          # Script d'exploration initial
├── construct_parser.py      # canvas Construct Parser
├── requirements.txt         # Dépendances Python
├── README.md                # Notes et mode d'emploi
└── .gitignore               # Pour versionner proprement
```

---

## Contenu des fichiers

### `requirements.txt`
```
construct>=2.10
hexdump
```

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
Lister et vérifier la sentinelle :
```bash
python construct_parser.py saves/ma_partie.sav
```

Modifier, par exemple, l’attaque de toutes les unités à 12 et écrire une nouvelle save :
```bash
python construct_parser.py saves/ma_partie.sav --all --field attack --value 12 --out saves/patched.sav
```

Modifier la défense des unités nommées “Weisz” :
```bash
python construct_parser.py saves/ma_partie.sav --unit-name Weisz --field defense --value 8 --out saves/weisz_def8.sav
```


### `.gitignore`
```
.venv/
__pycache__/
*.pyc
*.pyo
*.log
.DS_Store
```

---

## Étapes suivantes
- Créez un répertoire `saves/` pour stocker vos fichiers de test A/B/C.
- Enrichissez progressivement le parseur avec vos découvertes.

Ainsi vous avez une base de projet bien structurée, facile à versionner et à partager.

