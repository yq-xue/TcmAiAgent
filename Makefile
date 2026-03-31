.PHONY: run install

install:
\tpython3 -m pip install -U pip
\tpython3 -m pip install -r requirements.txt

run:
\tbash ./run.sh

