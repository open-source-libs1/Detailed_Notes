#!/bin/bash
# build_lambdas.sh
#
# One-command Lambda builder for LocalStack.
# For each Pipfile:
#   1) pipenv install   (ensures env exists, including internal libs)
#   2) pipenv run pip freeze -> .localstack/build/requirements_*.txt
#   3) pipenv run python -c "import site; print(site.getsitepackages()[0])"
#      to locate the env's site-packages
#   4) copy site-packages into build dir
#   5) copy lambda source + zip
#
# Outputs:
#   .localstack/artifacts/qsink_forwarder_lambda.zip
#   .localstack/artifacts/enrollment_writer_lambda.zip
#   .localstack/build/requirements_qsink.txt
#   .localstack/build/requirements_enrollment.txt

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

# Helper: ensure pipenv env exists for a Pipfile dir, write requirements into
# .localstack/build, and return that env's site-packages path.
build_env_and_get_sitepkgs() {
  local pipfile_dir="$1"     # directory containing Pipfile
  local req_out="$2"         # requirements file path under .localstack/build

  (
    set -euo pipefail
    cd "${pipfile_dir}"

    echo "[env][$(basename "${pipfile_dir}")] pipenv install..."
    pipenv install >/dev/null

    echo "[env][$(basename "${pipfile_dir}")] freezing -> ${req_out}"
    pipenv run pip freeze > "${req_out}"

    echo "[env][$(basename "${pipfile_dir}")] locating site-packages..."
    local sitepkg
    sitepkg=$(pipenv run python - << 'PY'
import site
paths = site.getsitepackages()
if not paths:
    raise SystemExit("No site-packages found via site.getsitepackages()")
print(paths[0])
PY
    )
    echo "[env][$(basename "${pipfile_dir}")] site-packages: ${sitepkg}"
    echo "${sitepkg}"
  )
}

# Generic builder for one lambda
build_lambda() {
  local name="$1"            # e.g. "qsink" or "enrollment"
  local pipfile_dir="$2"     # where Pipfile lives
  local src_dir="$3"         # where lambda code (handler.py, utils, etc.) lives

  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local build_subdir="${BUILD_DIR}/${name}_lambda"
  local zip_path="${ARTIFACT_DIR}/${name}_lambda.zip"

  echo ""
  echo "=== Building ${name} lambda ==="

  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  # 1) Ensure env + get site-packages; write requirements_* to .localstack/build
  local sitepkg
  sitepkg=$(build_env_and_get_sitepkgs "${pipfile_dir}" "${req_file}")

  # 2) Copy installed packages into build dir
  echo "[${name}] copying site-packages from ${sitepkg} -> ${build_subdir}"
  cp -R "${sitepkg}/." "${build_subdir}/"

  # 3) Copy lambda source
  echo "[${name}] copying source from ${src_dir}"
  cp -R "${src_dir}/." "${build_subdir}/"

  # 4) Zip
  echo "[${name}] creating zip -> ${zip_path}"
  ( cd "${build_subdir}" && zip -r "${zip_path}" . >/dev/null )

  echo "[${name}] DONE"
}

# ----------------- QSink Forwarder Lambda -----------------
# TODO: confirm QSINK_SRC points to the folder that has handler.py for QSink
QSINK_PIPFILE_DIR="${ROOT_DIR}/qsink-referrals-enrollment"
QSINK_SRC="${ROOT_DIR}/qsink-referrals-enrollment/src"

build_lambda "qsink" "${QSINK_PIPFILE_DIR}" "${QSINK_SRC}"

# ----------------- Enrollment Writer Lambda -----------------
# TODO: confirm ENR_SRC points to the folder that has handler.py for Enrollment Writer
ENR_PIPFILE_DIR="${ROOT_DIR}"                      # root Pipfile
ENR_SRC="${ROOT_DIR}/enrollment_writer/app"

build_lambda "enrollment" "${ENR_PIPFILE_DIR}" "${ENR_SRC}"

echo ""
echo "=========================="
echo "  BUILD COMPLETE"
echo "=========================="
echo "Artifacts in ${ARTIFACT_DIR}:"
ls -lh "${ARTIFACT_DIR}"
echo ""
echo "Requirements in ${BUILD_DIR}:"
ls -lh "${BUILD_DIR}"/requirements_*.txt || true
echo ""
