#!/bin/bash
# build_lambdas.sh
#
# Builds Lambda zips (code + deps) for LocalStack.
# - QSink forwarder uses its own Pipfile under qsink-referrals-enrollment/.
# - Enrollment Writer uses the main Pipfile at repo root.
#
# Instead of reinstalling from requirements.txt (which breaks for internal
# packages like c1-referralplatform-awsutil), we:
#   1) let pipenv install deps into its venv
#   2) locate that venv's site-packages
#   3) copy site-packages directly into the Lambda build directory
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

# Small helper: given a Pipfile directory, ensure pipenv env is ready and
# return its site-packages path.
get_site_packages() {
  local pipfile_dir="$1"
  (
    cd "${pipfile_dir}"
    echo "[build] [$(basename "${pipfile_dir}")] Ensuring pipenv environment is installed..."
    pipenv install >/dev/null

    # Ask the pipenv environment where its purelib (site-packages) is.
    local sp
    sp=$(pipenv run python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
    echo "${sp}"
  )
}

# ----------------- QSink forwarder -----------------
QSINK_PIPFILE_DIR="${ROOT_DIR}/qsink-referrals-enrollment"    # TODO: confirm path
QSINK_BUILD="${BUILD_DIR}/qsink_forwarder"
QSINK_ZIP="${ARTIFACT_DIR}/qsink_forwarder_lambda.zip"
QSINK_SRC="${ROOT_DIR}/qsink-referrals-enrollment/src"        # TODO: confirm path

rm -rf "${QSINK_BUILD}"
mkdir -p "${QSINK_BUILD}"

echo "[build] === QSink: building from ${QSINK_PIPFILE_DIR} ==="
QSINK_SITEPKG=$(get_site_packages "${QSINK_PIPFILE_DIR}")
echo "[build] [QSink] site-packages at: ${QSINK_SITEPKG}"

echo "[build] [QSink] Copying site-packages into ${QSINK_BUILD}"
cp -R "${QSINK_SITEPKG}/." "${QSINK_BUILD}/"

echo "[build] [QSink] Copying source from ${QSINK_SRC}"
cp -R "${QSINK_SRC}/." "${QSINK_BUILD}/"

echo "[build] [QSink] Creating zip -> ${QSINK_ZIP}"
( cd "${QSINK_BUILD}" && zip -r "${QSINK_ZIP}" . >/dev/null )


# ----------------- Enrollment Writer -----------------
ENR_PIPFILE_DIR="${ROOT_DIR}"                                  # root Pipfile
ENR_BUILD="${BUILD_DIR}/enrollment_writer"
ENR_ZIP="${ARTIFACT_DIR}/enrollment_writer_lambda.zip"
ENR_SRC="${ROOT_DIR}/enrollment_writer/app"                    # TODO: confirm path

rm -rf "${ENR_BUILD}"
mkdir -p "${ENR_BUILD}"

echo "[build] === Enrollment: building from ${ENR_PIPFILE_DIR} ==="
ENR_SITEPKG=$(get_site_packages "${ENR_PIPFILE_DIR}")
echo "[build] [Enrollment] site-packages at: ${ENR_SITEPKG}"

echo "[build] [Enrollment] Copying site-packages into ${ENR_BUILD}"
cp -R "${ENR_SITEPKG}/." "${ENR_BUILD}/"

echo "[build] [Enrollment] Copying source from ${ENR_SRC}"
cp -R "${ENR_SRC}/." "${ENR_BUILD}/"

echo "[build] [Enrollment] Creating zip -> ${ENR_ZIP}"
( cd "${ENR_BUILD}" && zip -r "${ENR_ZIP}" . >/dev/null )

echo "[build] DONE. Artifacts in ${ARTIFACT_DIR}:"
ls -lh "${ARTIFACT_DIR}"
