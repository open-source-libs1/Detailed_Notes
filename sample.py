# 0) sanity
which python3
python3 -V

# 1) make sure pip exists for this python (only needed if pip is missing)
python3 -m pip -V || python3 -m ensurepip --upgrade

# 2) make sure your corporate pip index is configured (per your doc)
mkdir -p ~/.config/pip
cat > ~/.config/pip/pip.conf <<'EOF'
[global]
index-url = https://artifactory.cloud.capitalone.com/artifactory/api/pypi/pypi-internalfacing/simple
# If TLS/proxy rules require it in your env, uncomment:
# trusted-host = artifactory.cloud.capitalone.com
EOF

# 3) install virtualenv for THIS python
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install --user virtualenv

# 4) now the doc step will work
python3 -m virtualenv smartopscli
source smartopscli/bin/activate

# 5) after activation, python will exist (inside the venv)
which python
python -V
