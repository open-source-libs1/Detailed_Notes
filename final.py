#!/bin/bash
# build_lambdas.sh
#
# Build Lambda deployment zips for LocalStack.
# We assume:
#   - QSink forwarder requirements: qsink-referrals-enrollment/requirements_lambda.txt
#   - Enrollment writer requirements: requirements_enrollment_lambda.txt (at repo root)
#
# Pattern:
#   pip install \
#       --platform manylinux2014_x86_64 \
#       --implementation cp \
#       --python-version 3.12 \
#       --target <build_dir> \
#       -r <requirements_file>
#
# Then copy source code into <build_dir> and zip it.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo "[build] Root dir: ${ROOT_DIR}"
echo "[build] Artifacts dir: ${ARTIFACT_DIR}"
echo "[build] Build dir: ${BUILD_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3.12}"   # change if your python cmd is different

install_deps() {
  local req_file="$1"
  local target_dir="$2"

  if [ ! -f "${req_file}" ]; then
    echo "[build][WARN] Requirements file not found: ${req_file}. Skipping deps."
    return 0
  fi

  echo "[build] Installing dependencies from ${req_file} into ${target_dir} ..."
  "${PYTHON_BIN}" -m pip install \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.12 \
    --target "${target_dir}" \
    --only-binary=:all: \
    --upgrade \
    -r "${req_file}"
}

# ----------------- QSink forwarder -----------------
QSINK_REQ="${ROOT_DIR}/qsink-referrals-enrollment/requirements_lambda.txt"   # TODO: adjust name/path if needed
QSINK_SRC="${ROOT_DIR}/qsink-referrals-enrollment/src"                       # TODO: confirm this is where handler.py lives
QSINK_BUILD="${BUILD_DIR}/qsink_forwarder"
QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder_lambda.zip"

rm -rf "${QSINK_BUILD}"
mkdir -p "${QSINK_BUILD}"

echo "[build] === QSink forwarder ==="
install_deps "${QSINK_REQ}" "${QSINK_BUILD}"

echo "[build] Copying QSink source from ${QSINK_SRC}"
cp -R "${QSINK_SRC}/." "${QSINK_BUILD}/"

echo "[build] Creating QSink zip -> ${QSINK_ZIP}"
( cd "${QSINK_BUILD}" && zip -r "${QSINK_ZIP}" . >/dev/null )

# ----------------- Enrollment writer -----------------
ENR_REQ="${ROOT_DIR}/requirements_enrollment_lambda.txt"       # from repo root
ENR_SRC="${ROOT_DIR}/enrollment_writer/app"                    # TODO: confirm handler location
ENR_BUILD="${BUILD_DIR}/enrollment_writer"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer_lambda.zip"

rm -rf "${ENR_BUILD}"
mkdir -p "${ENR_BUILD}"

echo "[build] === Enrollment writer ==="
install_deps "${ENR_REQ}" "${ENR_BUILD}"

echo "[build] Copying Enrollment source from ${ENR_SRC}"
cp -R "${ENR_SRC}/." "${ENR_BUILD}/"

echo "[build] Creating Enrollment zip -> ${ENR_ZIP}"
( cd "${ENR_BUILD}" && zip -r "${ENR_ZIP}" . >/dev/null )

echo "[build] DONE. Artifacts in ${ARTIFACT_DIR}:"
ls -lh "${ARTIFACT_DIR}"
