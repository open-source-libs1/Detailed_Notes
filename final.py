


python -m venv .venv


.\.venv\Scripts\activate


pip install --upgrade pip


pip install -r requirements.txt


pip install -r requirements-dev.txt


pytest


pytest --cov-fail-under=50 --cov-branch --cov-config=.coveragerc --cov=. tests -s

//////////////////

.\.venv\Scripts\activate
pytest --cov-fail-under=50 --cov-branch --cov-config=.coveragerc --cov=. tests -s
