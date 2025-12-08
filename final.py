#!/bin/bash
# build_lambdas.sh
#
# Build Lambda zips for LocalStack by reusing pipenv virtualenvs.
# No `--target`, no re-downloading internal packages.
#
# For each lambda:
#   1) pipenv install (ensures env + internal libs)
#   2) pipenv run pip freeze -> .localstack/build/requirements_<name>.txt
#   3) use `pipenv --venv` to find venv dir; locate lib/python*/site-packages
#   4) copy site-packages into .localstack/build/<name>_lambda
#   5) copy lambda source into that dir
#   6) zip -> .localstack/artifacts/<name>_lambda.zip

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

# Helper: prepare pipenv env, write requirements_<name>.txt under .localstack/build,
# and return the venv's site-packages path.
prepare_env_and_get_sitepkgs() {
  local pipfile_dir="$1"   # where Pipfile is
  local req_out="$2"       # requirements_<name>.txt path under .localstack/build

  (
    set -euo pipefail
    cd "${pipfile_dir}"

    local name
    name="$(basename "${pipfile_dir}")"
    echo "[env][${name}] running pipenv install..."
    pipenv install >/dev/null

    echo "[env][${name}] freezing env -> ${req_out}"
    pipenv run pip freeze > "${req_out}"

    echo "[env][${name}] locating venv via 'pipenv --venv'..."
    local venv_dir
    venv_dir="$(pipenv --venv)"
    echo "[env][${name}] venv dir: ${venv_dir}"

    echo "[env][${name}] searching for site-packages under ${venv_dir}/lib..."
    # Use shell glob; first match wins
    shopt -s nullglob
    local candidates=( "${venv_dir}"/lib/python*/site-packages )
    shopt -u nullglob

    if [ "${#candidates[@]}" -eq 0 ] || [ ! -d "${candidates[0]}" ]; then
      echo "[env][${name}] ERROR: could not find site-packages under ${venv_dir}/lib" >&2
      echo "[env][${name}]       Run 'ls \"${venv_dir}\"/lib' manually to inspect." >&2
      exit 1
    fi

    local sitepkg="${candidates[0]}"
    echo "[env][${name}] using site-packages: ${sitepkg}"

    # Return site-packages path to caller
    echo "${sitepkg}"
  )
}

build_lambda() {
  local name="$1"          # "qsink" or "enrollment"
  local pipfile_dir="$2"   # directory containing Pipfile
  local src_dir="$3"       # directory containing lambda source (handler.py etc.)

  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local build_subdir="${BUILD_DIR}/${name}_lambda"
  local zip_path="${ARTIFACT_DIR}/${name}_lambda.zip"

  echo ""
  echo "=== Building ${name} lambda ==="

  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  # 1) ensure env, write requirements_<name>.txt, get site-packages path
  local sitepkg
  sitepkg="$(prepare_env_and_get_sitepkgs "${pipfile_dir}" "${req_file}")"

  # 2) copy installed deps
  echo "[${name}] copying site-packages from ${sitepkg} -> ${build_subdir}"
  cp -R "${sitepkg}/." "${build_subdir}/"

  # 3) copy lambda source
  echo "[${name}] copying source from ${src_dir}"
  cp -R "${src_dir}/." "${build_subdir}/"

  # 4) zip
  echo "[${name}] creating zip -> ${zip_path}"
  ( cd "${build_subdir}" && zip -r "${zip_path}" . >/dev/null )

  echo "[${name}] DONE"
}

# ----------------- QSink Forwarder Lambda -----------------
# TODO: confirm QSINK_SRC points to folder housing QSink lambda handler (e.g. handler.py)
QSINK_PIPFILE_DIR="${ROOT_DIR}/qsink-referrals-enrollment"
QSINK_SRC="${ROOT_DIR}/qsink-referrals-enrollment/src"

build_lambda "qsink" "${QSINK_PIPFILE_DIR}" "${QSINK_SRC}"

# ----------------- Enrollment Writer Lambda -----------------
# TODO: confirm ENR_SRC points to folder housing Enrollment Writer handler
ENR_PIPFILE_DIR="${ROOT_DIR}"                     # root Pipfile
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
