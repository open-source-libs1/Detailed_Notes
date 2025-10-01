cd ~/Desktop/Projects/oct-1/enrollment/qsink-referrals-enrollment && \
source ../../.venv/bin/activate && \
export PYTHONPATH="$(pwd)" && \
coverage run -m unittest -v tests.utils.test_helpers && \
coverage report -m --include="$(pwd)/src/utils/helpers.py"
