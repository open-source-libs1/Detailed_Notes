#!/bin/bash
#
# build_lambdas.sh
#
# Build Lambda deployment ZIPs for LocalStack.
#
# We have two Python Lambdas:
#   1) QSink Forwarder      (qsink-referrals-enrollment)
#   2) Enrollment Writer    (enrollment_writer)
#
# Both use Pipenv. To avoid all the issues with re-installing internal
# packages (like c1-referralplatform-awsutil) into a separate target
# directory, we:
#
#   - Reuse the existing Pipenv virtualenvs.
#   - Copy their site-packages into a Lambda build dir.
#   - Copy the lambda source on top.
#   - Zip the result.
#
# This is exactly equivalent to:
#   pipenv install
#   VENV=$(pipenv --venv)
#   SITEPKG=$(ls -d "$VENV"/lib/python*/site-packages)
#   cp -R "$SITEPKG"/. build_dir/
#   cp -R src/. build_dir/
#   zip -r lambda.zip build_dir
#
# which you have already validated works on your machine.

set -euo pipefail

#############################
# Repo paths / configuration
#############################

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

# QSink Forwarder Lambda
QSINK_NAME="qsink_forwarder"
QSINK_PIPFILE_DIR="${ROOT_DIR}/qsink-referrals-enrollment"   # Pipfile location
QSINK_SRC_DIR="${ROOT_DIR}/qsink-referrals-enrollment/src"   # Lambda code (handler.py etc.)

# Enrollment Writer Lambda
ENR_NAME="enrollment_writer"
ENR_PIPFILE_DIR="${ROOT_DIR}"                                # Root Pipfile
ENR_SRC_DIR="${ROOT_DIR}/enrollment_writer/app"              # Lambda code

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo ""
echo "=========================="
echo "  BUILDING LAMBDA ZIPS"
echo "=========================="
echo "ROOT_DIR     = ${ROOT_DIR}"
echo "ARTIFACT_DIR = ${ARTIFACT_DIR}"
echo "BUILD_DIR    = ${BUILD_DIR}"
echo ""

#####################################
# Helper: build a single Lambda ZIP #
#####################################
# Args:
#   $1 = logical name       (for logs + filenames)
#   $2 = Pipfile directory  (where Pipfile lives)
#   $3 = source directory   (where handler.py & code live)
#
# Steps:
#   - Clean build dir
#   - In Pipfile dir:
#       * pipenv install
#       * pipenv run pip freeze -> .localstack/build/requirements_<name>.txt
#       * VENV=$(pipenv --venv)
#       * SITEPKG=$(ls -d "$VENV"/lib/python*/site-packages | head -1)
#       * cp site-packages -> build dir
#   - Copy source into build dir
#   - Zip build dir into .localstack/artifacts/<name>.zip

build_lambda() {
  local name="$1"
  local pipfile_dir="$2"
  local src_dir="$3"

  local build_subdir="${BUILD_DIR}/${name}_lambda"
  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local zip_path="${ARTIFACT_DIR}/${name}.zip"

  echo ""
  echo "=== Building '${name}' lambda ==="
  echo "[${name}] Pipfile dir : ${pipfile_dir}"
  echo "[${name}] Source dir   : ${src_dir}"
  echo "[${name}] Build dir    : ${build_subdir}"
  echo "[${name}] Artifact     : ${zip_path}"

  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  # Do all env-related work inside the Pipfile directory
  (
    set -euo pipefail
    cd "${pipfile_dir}"

    echo "[${name}] pipenv install (ensuring env is up to date)..."
    pipenv install >/dev/null

    echo "[${name}] Freezing env -> ${req_file}"
    pipenv run pip freeze > "${req_file}"

    echo "[${name}] Resolving virtualenv path via 'pipenv --venv'..."
    VENV_DIR="$(pipenv --venv)"
    echo "[${name}] VENV_DIR = ${VENV_DIR}"

    echo "[${name}] Locating site-packages under \${VENV_DIR}/lib..."
    # This mirrors the manual commands you already ran:
    #   ls "$VENV"/lib
    #   ls -d "$VENV"/lib/python*/site-packages
    SITEPKG_CANDIDATE=$(ls -d "${VENV_DIR}"/lib/python*/site-packages 2>/dev/null | head -1 || true)

    if [[ -z "${SITEPKG_CANDIDATE}" || ! -d "${SITEPKG_CANDIDATE}" ]]; then
      echo "[${name}] ERROR: Could not find site-packages under ${VENV_DIR}/lib/python*/site-packages" >&2
      echo "[${name}]        Run these manually to debug:" >&2
      echo "[${name}]          cd ${pipfile_dir}" >&2
      echo "[${name}]          VENV=\$(pipenv --venv)" >&2
      echo "[${name}]          ls \"\$VENV\"/lib" >&2
      echo "[${name}]          ls -d \"\$VENV\"/lib/python*/site-packages" >&2
      exit 1
    fi

    echo "[${name}] Using site-packages: ${SITEPKG_CANDIDATE}"
    echo "[${name}] Copying dependencies -> ${build_subdir}"
    cp -R "${SITEPKG_CANDIDATE}/." "${build_subdir}/"
  )

  echo "[${name}] Copying lambda source -> ${build_subdir}"
  cp -R "${src_dir}/." "${build_subdir}/"

  echo "[${name}] Creating deployment zip -> ${zip_path}"
  (
    cd "${build_subdir}"
    zip -r "${zip_path}" . >/dev/null
  )

  echo "[${name}] DONE"
}

###############################
# Build both lambda artifacts #
###############################

build_lambda "${QSINK_NAME}" "${QSINK_PIPFILE_DIR}" "${QSINK_SRC_DIR}"
build_lambda "${ENR_NAME}"   "${ENR_PIPFILE_DIR}"   "${ENR_SRC_DIR}"

echo ""
echo "=========================="
echo "  BUILD COMPLETE"
echo "=========================="
ls -lh "${ARTIFACT_DIR}" || true
echo ""
echo "Requirements snapshots in ${BUILD_DIR}:"
ls -lh "${BUILD_DIR}"/requirements_*.txt || true
echo ""
