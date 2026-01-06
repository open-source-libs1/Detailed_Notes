PY312="$(brew --prefix python@3.12)/bin/python3.12"
echo "$PY312"
"$PY312" -V


deactivate 2>/dev/null || true
cd ~/Desktop/Projects/jan-1

# delete the old python3.14 venv
rm -rf smartopscli



"$PY312" -m venv smartopscli
source smartopscli/bin/activate



python -V
which python
pip -V



python -m pip install --upgrade pip setuptools wheel


pip install --no-cache-dir c1-smartops
