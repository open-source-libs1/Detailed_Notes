# 1) exit old venv
deactivate 2>/dev/null || true

# 2) install a supported python (pick one)
brew install python@3.12

# 3) recreate venv using python3.12 explicitly
cd ~/Desktop/Projects/jan-1
rm -rf smartopscli
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv smartopscli
source smartopscli/bin/activate

# 4) upgrade tooling inside venv
python -m pip install --upgrade pip setuptools wheel

# 5) install SmartOps CLI
pip install --no-cache-dir c1-smartops
