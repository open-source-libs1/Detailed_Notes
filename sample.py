cd /path/to/your/repo/lambda
export PATH="$HOME/.local/bin:$PATH"            # so pipenv is found
export PIPENV_VENV_IN_PROJECT=1

# make sure Pipfile has pydantic==2.11.7 (you already added it)
pipenv sync --dev || pipenv install --dev       # installs pydantic + your internal pkg

# quick check that pydantic is in the venv
pipenv run python -c "import pydantic; print(pydantic.__version__)"


#########################################


import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
# now import from src
from src.utils.database_utils import get_db_params




##########################################

export PYTHONPATH="$PWD/src"    # keep this in the shell
pipenv run pytest -q --cov=src --cov-report=term-missing
