xattr -l fix_pipenv_312.sh 2>/dev/null || echo "No xattr on file"

xattr -d com.apple.quarantine fix_pipenv_312.sh 2>/dev/null || true

./fix_pipenv_312.sh
