


cd ~/Desktop/Projects/oct-1
source .venv/bin/activate
cd enrollment
export PYTHONPATH="$(pwd)/src:$(pwd)/src/utils:$PYTHONPATH"

# run only the helpers tests:
coverage run -m unittest tests.utils.test_helpers -v
coverage report -m




coverage run -m unittest tests.test_helpers -v && coverage report -m
