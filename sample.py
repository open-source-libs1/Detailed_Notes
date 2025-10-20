



PIPENV_IGNORE_VIRTUALENVS=1 pipenv sync --dev


pipenv run pytest --maxfail=1 --disable-warnings --cov=src --cov-report=term-missing -q



pipenv run pytest tests/test_main.py -q
pipenv run pytest tests/test_main.py::TestHandler::test_201 -q
