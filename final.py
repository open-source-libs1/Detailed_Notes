#!/bin/bash
#
# build_lambdas.sh
#
# Purpose
# -------
# Build Lambda deployment ZIPs for running the enrollment stack against LocalStack.
# We have two Python Lambdas:
#   1) QSink Forwarder      (qsink-referrals-enrollment)
#   2) Enrollment Writer    (enrollment_writer)
#
# Each Lambda uses Pipenv for dependency management. We *reuse* those Pipenv
# virtualenvs to avoid re-resolving internal/private packages (e.g. c1-*
# libraries) that may only be available from internal indexes.
#
# High-level flow for each Lambda:
#   - Ensure its Pipenv environment is created and up to date (`pipenv install`).
#   - Freeze its environment to a requirements_<name>.txt (for traceability).
#   - Locate the Pipenv virtualenv and its site-packages directory.
#   - Copy site-packages (all installed deps) into a Lambda build directory.
#   - Copy the Lambda's application source into the same directory.
#   - Zip the directory into .localstack/artifacts/<name>_lambda.zip.
#
# This script is intentionally idempotent: rerunning it will rebuild both ZIPs
# from scratch, overwriting any previous artifacts.
#

set -euo pipefail

########################################
# Repo-relative paths / configuration #
########################################

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/.localstack/artifacts"
BUILD_DIR="${ROOT_DIR}/.localstack/build"

# QSink Forwarder Lambda
QSINK_PIPFILE_DIR="${ROOT_DIR}/qsink-referrals-enrollment"     # Pipfile location
QSINK_SRC_DIR="${ROOT_DIR}/qsink-referrals-enrollment/src"     # Lambda source (handler.py, etc.)
QSINK_NAME="qsink_forwarder"

# Enrollment Writer Lambda
ENR_PIPFILE_DIR="${ROOT_DIR}"                                  # Root Pipfile
ENR_SRC_DIR="${ROOT_DIR}/enrollment_writer/app"                # Lambda source
ENR_NAME="enrollment_writer"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

echo ""
echo "=========================="
echo "  BUILDING LAMBDA ZIPS"
echo "=========================="
echo "ROOT_DIR       = ${ROOT_DIR}"
echo "ARTIFACT_DIR   = ${ARTIFACT_DIR}"
echo "BUILD_DIR      = ${BUILD_DIR}"
echo ""

########################################
# Helper: resolve site-packages for a #
# Pipenv environment                  #
########################################
# Given a directory containing a Pipfile, this function:
#   - ensures the Pipenv env exists (`pipenv install`)
#   - writes a requirements_<name>.txt under .localstack/build
#   - returns the absolute path to that env's site-packages directory
#
# We call Python *inside* the Pipenv env (`pipenv run python`) so paths are
# resolved against the correct virtualenv, not the system interpreter.

prepare_env_and_get_sitepkgs() {
  local pipfile_dir="$1"      # directory containing Pipfile
  local req_out="$2"          # path to requirements_<name>.txt
  local label="$3"            # human-friendly label for logging

  (
    set -euo pipefail
    cd "${pipfile_dir}"

    echo "[env][${label}] Running 'pipenv install' to ensure environment..."
    pipenv install >/dev/null

    echo "[env][${label}] Freezing environment -> ${req_out}"
    pipenv run pip freeze > "${req_out}"

    echo "[env][${label}] Resolving site-packages via 'pipenv run python'..."
    # We prefer sysconfig['purelib'], but also fall back to site.getsitepackages()
    local sitepkg
    sitepkg="$(
      pipenv run python - << 'PY'
import os
import sysconfig
import site

candidates = []

purelib = sysconfig.get_paths().get("purelib")
if purelib:
    candidates.append(purelib)

for p in site.getsitepackages():
    candidates.append(p)

for path in candidates:
    if path and os.path.isdir(path):
        print(path)
        break
PY
    )"

    if [ -z "${sitepkg}" ] || [ ! -d "${sitepkg}" ]; then
      echo "[env][${label}] ERROR: Could not resolve site-packages directory." >&2
      echo "[env][${label}]       Run 'pipenv --venv' and inspect <venv>/lib/python*/site-packages." >&2
      exit 1
    fi

    echo "[env][${label}] Using site-packages: ${sitepkg}"
    # Echo site-packages path back to caller
    echo "${sitepkg}"
  )
}

########################################
# Helper: build one Lambda artifact   #
########################################
# Arguments:
#   $1 = logical lambda name (for logging / filenames)
#   $2 = Pipfile directory for this lambda
#   $3 = source directory (code to copy into zip)

build_lambda() {
  local name="$1"
  local pipfile_dir="$2"
  local src_dir="$3"

  local build_subdir="${BUILD_DIR}/${name}_lambda"
  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local zip_path="${ARTIFACT_DIR}/${name}_lambda.zip"

  echo ""
  echo "=== Building '${name}' lambda ==="
  echo "[${name}] Pipfile dir : ${pipfile_dir}"
  echo "[${name}] Source dir   : ${src_dir}"
  echo "[${name}] Build dir    : ${build_subdir}"
  echo "[${name}] Artifact     : ${zip_path}"

  # Clean build directory to avoid stale files between runs
  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  # 1) Ensure Pipenv env, write requirements_<name>.txt, and get site-packages path
  local sitepkg
  sitepkg="$(prepare_env_and_get_sitepkgs "${pipfile_dir}" "${req_file}" "${name}")"

  # 2) Copy all installed dependencies into the build directory
  #    This effectively "vendorizes" the env's site-packages for Lambda.
  echo "[${name}] Copying dependencies from site-packages -> build dir..."
  cp -R "${sitepkg}/." "${build_subdir}/"

  # 3) Copy the lambda's application code on top of the dependencies
  echo "[${name}] Copying lambda source -> build dir..."
  cp -R "${src_dir}/." "${build_subdir}/"

  # 4) Zip the build directory into an artifact
  echo "[${name}] Creating deployment zip..."
  (
    cd "${build_subdir}"
    zip -r "${zip_path}" . >/dev/null
  )

  echo "[${name}] DONE: ${zip_path}"
}

##########################
# Build both Lambdas    #
##########################

# QSink Forwarder (QSync → Enrollment queue)
build_lambda "${QSINK_NAME}" "${QSINK_PIPFILE_DIR}" "${QSINK_SRC_DIR}"

# Enrollment Writer (Enrollment SQS → Aurora DB writer)
build_lambda "${ENR_NAME}" "${ENR_PIPFILE_DIR}" "${ENR_SRC_DIR}"

echo ""
echo "=========================="
echo "  BUILD COMPLETE"
echo "=========================="
echo "Artifacts in ${ARTIFACT_DIR}:"
ls -lh "${ARTIFACT_DIR}" || true
echo ""
echo "Requirements snapshots in ${BUILD_DIR}:"
ls -lh "${BUILD_DIR}"/requirements_*.txt || true
echo ""
