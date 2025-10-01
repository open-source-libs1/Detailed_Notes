cd ~/Desktop/Projects/oct-1 && source .venv/bin/activate && cd enrollment \
&& export PYTHONPATH="$(pwd)/src:$(pwd)/src/utils" \
&& coverage run -m unittest -v tests.utils.test_helpers \
&& coverage report -m --include="$(pwd)/src/utils/helpers.py"
