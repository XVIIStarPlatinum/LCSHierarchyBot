python -m pip install --upgrade pip

pip install -r requirements.txt

if test -f tests/requirements-test.txt; then
	pip install -r tests/requirements-test.txt
fi

