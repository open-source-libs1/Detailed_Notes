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

echo "[build] Root dir: ${ROOT_DIR}"
echo "[build] Artifacts dir: ${ARTIFACT_DIR}"
echo "[build] Build dir: ${BUILD_DIR}"

# ----------------- QSink deps from its own Pipfile -----------------
QSINK_PIPFILE_DIR="${ROOT_DIR}/qsink-referrals-enrollment"   # TODO: confirm this path
QSINK_REQ="${BUILD_DIR}/requirements_qsink.txt"
QSINK_BUILD="${BUILD_DIR}/qsink_forwarder"
QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder_lambda.zip"

# TODO: set this to the directory where your QSink lambda code (handler.py etc.) lives
QSINK_SRC="${ROOT_DIR}/qsink-referrals-enrollment/src"

rm -rf "${QSINK_BUILD}"
mkdir -p "${QSINK_BUILD}"

echo "[build] === QSink: using Pipfile at ${QSINK_PIPFILE_DIR} ==="
(
  cd "${QSINK_PIPFILE_DIR}"
  echo "[build][QSink] Ensuring pipenv environment is installed..."
  pipenv install >/dev/null

  echo "[build][QSink] Freezing deps from pipenv env -> ${QSINK_REQ}"
  pipenv run pip freeze > "${QSINK_REQ}"

  echo "[build][QSink] Installing deps from pipenv env into ${QSINK_BUILD}"
  # IMPORTANT: use pipenv's pip, so it can see internal indexes (c1-* packages etc.)
  pipenv run pip install -r "${QSINK_REQ}" -t "${QSINK_BUILD}"
)

echo "[build][QSink] Copying source from ${QSINK_SRC}"
cp -R "${QSINK_SRC}/." "${QSINK_BUILD}/"

echo "[build][QSink] Creating zip -> ${QSINK_ZIP}"
( cd "${QSINK_BUILD}" && zip -r "${QSINK_ZIP}" . >/dev/null )


# ----------------- Enrollment Writer deps from root Pipfile -----------------
ENR_PIPFILE_DIR="${ROOT_DIR}"   # main Pipfile at repo root
ENR_REQ="${BUILD_DIR}/requirements_enrollment.txt"
ENR_BUILD="${BUILD_DIR}/enrollment_writer"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer_lambda.zip"

# TODO: set this to the directory where your Enrollment Writer lambda code lives
ENR_SRC="${ROOT_DIR}/enrollment_writer/app"

rm -rf "${ENR_BUILD}"
mkdir -p "${ENR_BUILD}"

echo "[build] === Enrollment: using Pipfile at ${ENR_PIPFILE_DIR} ==="
(
  cd "${ENR_PIPFILE_DIR}"
  echo "[build][Enrollment] Ensuring pipenv environment is installed..."
  pipenv install >/dev/null

  echo "[build][Enrollment] Freezing deps from pipenv env -> ${ENR_REQ}"
  pipenv run pip freeze > "${ENR_REQ}"

  echo "[build][Enrollment] Installing deps from pipenv env into ${ENR_BUILD}"
  pipenv run pip install -r "${ENR_REQ}" -t "${ENR_BUILD}"
)

echo "[build][Enrollment] Copying source from ${ENR_SRC}"
cp -R "${ENR_SRC}/." "${ENR_BUILD}/"

echo "[build][Enrollment] Creating zip -> ${ENR_ZIP}"
( cd "${ENR_BUILD}" && zip -r "${ENR_ZIP}" . >/dev/null )

echo "[build] DONE. Artifacts in ${ARTIFACT_DIR}:"
ls -lh "${ARTIFACT_DIR}"
