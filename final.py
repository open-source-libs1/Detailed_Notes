#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo ""
echo "============================"
echo "   BUILDING LAMBDA ZIPS"
echo "============================"
echo ""

build_lambda() {
    local name="$1"
    local pipfile_dir="$2"
    local src_dir="$3"

    local lambda_build="${BUILD_DIR}/${name}_lambda"
    local req_file="${BUILD_DIR}/requirements_${name}.txt"
    local zip_path="${ARTIFACT_DIR}/${name}.zip"

    echo ""
    echo "=== Building ${name} ==="

    rm -rf "${lambda_build}"
    mkdir -p "${lambda_build}"

    (
        cd "${pipfile_dir}"

        echo "[${name}] pipenv install..."
        pipenv install >/dev/null

        echo "[${name}] generating requirements..."
        pipenv run pip freeze > "${req_file}"

        echo "[${name}] getting venv path..."
        VENV_PATH=$(pipenv --venv)
        echo "[${name}] VENV = ${VENV_PATH}"

        SITEPKG=$(python3 - <<EOF
import site, sys
paths = site.getsitepackages()
for p in paths:
    if "site-packages" in p:
        print(p)
        sys.exit(0)
print("")
EOF
)

        if [[ -z "$SITEPKG" ]]; then
            echo "[${name}] FALLBACK: scanning venv dirs..."
            SITEPKG=$(find "$VENV_PATH" -type d -path "*/site-packages" | head -1)
        fi

        echo "[${name}] SITE-PACKAGES = ${SITEPKG}"

        if [[ ! -d "$SITEPKG" ]]; then
            echo "[${name}] ERROR: cannot find site-packages under $VENV_PATH" >&2
            exit 1
        fi

        echo "[${name}] copying dependencies..."
        cp -R "${SITEPKG}/." "${lambda_build}/"
    )

    echo "[${name}] copying source..."
    cp -R "${src_dir}/." "${lambda_build}/"

    echo "[${name}] creating zip..."
    (cd "${lambda_build}" && zip -r "${zip_path}" . >/dev/null)

    echo "[${name}] DONE -> ${zip_path}"
}

# ----------------------
# QSYNC FORWARDER
# ----------------------
build_lambda \
    "qsink_forwarder" \
    "${ROOT_DIR}/qsink-referrals-enrollment" \
    "${ROOT_DIR}/qsink-referrals-enrollment/src"

# ----------------------
# ENROLLMENT WRITER
# ----------------------
build_lambda \
    "enrollment_writer" \
    "${ROOT_DIR}" \
    "${ROOT_DIR}/enrollment_writer/app"

echo ""
echo "============================"
echo "     BUILD COMPLETE"
echo "============================"
ls -lh "${ARTIFACT_DIR}"
echo ""
