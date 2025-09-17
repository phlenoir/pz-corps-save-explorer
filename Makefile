venv:
	python -m venv .venv
	. .venv/bin/activate; pip install -r requirements.txt

run:
	. .venv/bin/activate; python explore_save.py sample.sav

kaitai:
	kaitai-struct-compiler -t python panzer_corps_save.ksy -d kaitai/