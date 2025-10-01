cd ~/Desktop/Projects/oct-1 && source .venv/bin/activate && cd enrollment \
&& export PYTHONPATH="$(pwd)/src:$(pwd)/src/utils:$PYTHONPATH" \
&& coverage run -m unittest discover -s . -p "test_*.py" -v && coverage report -m
