#!/bin/bash
# build_lambdas.sh
#
# One-command Lambda builder for LocalStack.
# Automates:
#   ✔ pipenv install (for both projects)
#   ✔ pipenv freeze > requirements.txt
#   ✔ pip install --target <build> -r requirements.txt
#   ✔ copy source code
#   ✔ create zip artifacts
#
# Outputs:
#   .localstack/artifacts/qsink_forwarder_lambda.zip
#   .localstack/artifacts/enrollment_writer_lambda.zip

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo ""
echo "=========================="
echo "  BUILDING LAMBDA ZIPS"
echo "=========================="
echo ""

PYTHON_BIN="${PYTHON_BIN:-python3.12}"

#
# Helper function to:
#   1. pipenv install
#   2. pipenv freeze -> requirements
#
generate_requirements() {
  local pipfile_dir="$1"
  local output_req_file="$2"

  echo ""
  echo "[req] Generating requirements for: ${pipfile_dir}"
  (
    cd "${pipfile_dir}"
    echo "[req] Running pipenv install..."
    pipenv install >/dev/null

    echo "[req] Freezing environment -> ${output_req_file}"
    pipenv run pip freeze > "${output_req_file}"
  )
}

#
# Helper to install dependencies into Lambda build dir.
#
install_deps() {
  local req_file="$1"
  local target_dir="$2"

  echo ""
  echo "[deps] Installing deps from ${req_file} into ${target_dir}"

  "${PYTHON_BIN}" -m pip install \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.12 \
    --target "${target_dir}" \
    --upgrade \
    -r "${req_file}"
}

#
# -------------------------------
#    QSink Forwarder Lambda
# -------------------------------
#

QSINK_DIR="${ROOT_DIR}/qsink-referrals-enrollment"
QSINK_REQ="${QSINK_DIR}/requirements_lambda.txt"
QSINK_SRC="${QSINK_DIR}/src"               # TODO confirm handler path
QSINK_BUILD="${BUILD_DIR}/qsink_forwarder"
QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder_lambda.zip"

rm -rf "${QSINK_BUILD}"
mkdir -p "${QSINK_BUILD}"

echo ""
echo "=== Building QSink Forwarder Lambda ==="

generate_requirements "${QSINK_DIR}" "${QSINK_REQ}"
install_deps "${QSINK_REQ}" "${QSINK_BUILD}"

echo "[qsink] Copying source code..."
cp -R "${QSINK_SRC}/." "${QSINK_BUILD}/"

echo "[qsink] Creating lambda zip -> ${QSINK_ZIP}"
( cd "${QSINK_BUILD}" && zip -r "${QSINK_ZIP}" . >/dev/null )


#
# -------------------------------
#    Enrollment Writer Lambda
# -------------------------------
#

ENR_DIR="${ROOT_DIR}"                       # root Pipfile
ENR_REQ="${ROOT_DIR}/requirements_enrollment_lambda.txt"
ENR_SRC="${ROOT_DIR}/enrollment_writer/app" # TODO confirm handler path
ENR_BUILD="${BUILD_DIR}/enrollment_writer"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer_lambda.zip"

rm -rf "${ENR_BUILD}"
mkdir -p "${ENR_BUILD}"

echo ""
echo "=== Building Enrollment Writer Lambda ==="

generate_requirements "${ENR_DIR}" "${ENR_REQ}"
install_deps "${ENR_REQ}" "${ENR_BUILD}"

echo "[enrollment] Copying source code..."
cp -R "${ENR_SRC}/." "${ENR_BUILD}/"

echo "[enrollment] Creating lambda zip -> ${ENR_ZIP}"
( cd "${ENR_BUILD}" && zip -r "${ENR_ZIP}" . >/dev/null )


#
# Done
#
echo ""
echo "=========================="
echo "   BUILD COMPLETE"
echo "=========================="
echo "Artifacts:"
ls -lh "${ARTIFACT_DIR}"
echo ""
