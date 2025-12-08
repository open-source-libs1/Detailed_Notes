#!/bin/bash
# build_lambdas.sh
#
# Builds Lambda zips (code + deps) for LocalStack.
# QSink forwarder uses its own Pipfile under qsink-referrals-enrollment/.
# Enrollment Writer uses the main Pipfile at repo root.
#
# Result:
#   .localstack/artifacts/qsink_forwarder_lambda.zip
#   .localstack/artifacts/enrollment_writer_lambda.zip

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3.12}"

echo "[build] Using Python: ${PYTHON_BIN}"

# ----------------- QSink deps from its own Pipfile -----------------
QSINK_PIPFILE_DIR="${ROOT_DIR}/qsink-referrals-enrollment"   # TODO: confirm this path
QSINK_REQ="${BUILD_DIR}/requirements_qsink.txt"
rm -f "${QSINK_REQ}"

echo "[build] Generating QSink requirements from Pipfile in ${QSINK_PIPFILE_DIR}"
(
  cd "${QSINK_PIPFILE_DIR}"
  # NOTE: your pipenv version uses --requirements (long form), not -r
  pipenv lock --requirements > "${QSINK_REQ}"
)

# ----------------- Enrollment deps from root Pipfile -----------------
ENR_PIPFILE_DIR="${ROOT_DIR}"   # root Pipfile for enrollment writer
ENR_REQ="${BUILD_DIR}/requirements_enrollment.txt"
rm -f "${ENR_REQ}"

echo "[build] Generating Enrollment requirements from Pipfile in ${ENR_PIPFILE_DIR}"
(
  cd "${ENR_PIPFILE_DIR}"
  pipenv lock --requirements > "${ENR_REQ}"
)

# ----------------- Build QSink ZIP -----------------
# TODO: set this to the directory where your QSink lambda code (handler.py etc.) lives.
QSINK_SRC="${ROOT_DIR}/qsink-referrals-enrollment/src"
QSINK_BUILD="${BUILD_DIR}/qsink_forwarder"
QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder_lambda.zip"

rm -rf "${QSINK_BUILD}"
mkdir -p "${QSINK_BUILD}"

echo "[build] Installing QSink deps into ${QSINK_BUILD}"
"${PYTHON_BIN}" -m pip install -r "${QSINK_REQ}" -t "${QSINK_BUILD}"

echo "[build] Copying QSink source from ${QSINK_SRC}"
cp -R "${QSINK_SRC}/." "${QSINK_BUILD}/"

echo "[build] Creating QSink zip -> ${QSINK_ZIP}"
( cd "${QSINK_BUILD}" && zip -r "${QSINK_ZIP}" . >/dev/null )

# ----------------- Build Enrollment Writer ZIP -----------------
# TODO: set this to the directory where your Enrollment Writer lambda code lives.
ENR_SRC="${ROOT_DIR}/enrollment_writer/app"
ENR_BUILD="${BUILD_DIR}/enrollment_writer"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer_lambda.zip"

rm -rf "${ENR_BUILD}"
mkdir -p "${ENR_BUILD}"

echo "[build] Installing Enrollment deps into ${ENR_BUILD}"
"${PYTHON_BIN}" -m pip install -r "${ENR_REQ}" -t "${ENR_BUILD}"

echo "[build] Copying Enrollment source from ${ENR_SRC}"
cp -R "${ENR_SRC}/." "${ENR_BUILD}/"

echo "[build] Creating Enrollment zip -> ${ENR_ZIP}"
( cd "${ENR_BUILD}" && zip -r "${ENR_ZIP}" . >/dev/null )

echo "[build] DONE. Artifacts in ${ARTIFACT_DIR}:"
ls -lh "${ARTIFACT_DIR}"

