#!/bin/bash
# build_lambdas.sh
#
# One-command Lambda builder for LocalStack.
#
# For each lambda (qsink + enrollment):
#   1) pipenv install  (uses Pipfile/Pipfile.lock)
#   2) pipenv run pip freeze -> .localstack/build/requirements_<name>.txt
#   3) pipenv run pip install -r requirements_<name>.txt -t <build_dir>
#   4) copy lambda source into <build_dir>
#   5) zip -> .localstack/artifacts/<name>_lambda.zip

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

# Helper: runs inside a Pipfile directory, ensures env and writes requirements
generate_requirements() {
  local pipfile_dir="$1"
  local req_out="$2"
  (
    set -euo pipefail
    cd "${pipfile_dir}"
    echo "[req][$(basename "${pipfile_dir}")] pipenv install..."
    pipenv install >/dev/null

    echo "[req][$(basename "${pipfile_dir}")] freezing -> ${req_out}"
    pipenv run pip freeze > "${req_out}"
  )
}

# Helper: install deps from requirements into target dir using the SAME pipenv env
install_deps_with_pipenv() {
  local pipfile_dir="$1"
  local req_file="$2"
  local target_dir="$3"
  (
    set -euo pipefail
    cd "${pipfile_dir}"
    echo "[deps][$(basename "${pipfile_dir}")] installing from ${req_file} into ${target_dir}"
    # IMPORTANT: use pipenv's pip directly (matches your manual working command)
    pipenv run pip install \
      --upgrade \
      --target "${target_dir}" \
      -r "${req_file}"
  )
}

build_lambda() {
  local name="$1"        # "qsink" or "enrollment"
  local pipfile_dir="$2" # where Pipfile lives
  local src_dir="$3"     # where handler.py & code live

  local req_file="${BUILD_DIR}/requirements_${name}.txt"
  local build_subdir="${BUILD_DIR}/${name}_lambda"
  local zip_path="${ARTIFACT_DIR}/${name}_lambda.zip"

  echo ""
  echo "=== Building ${name} lambda ==="

  rm -rf "${build_subdir}"
  mkdir -p "${build_subdir}"

  # 1) generate requirements_<name>.txt in .localstack/build
  generate_requirements "${pipfile_dir}" "${req_file}"

  # 2) install deps into build_subdir using pipenv's pip
  install_deps_with_pipenv "${pipfile_dir}" "${req_file}" "${build_subdir}"

  # 3) copy source
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
