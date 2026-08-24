#!/usr/bin/env bash
# DevMind-AI 发布打包脚本（Linux / macOS / WSL）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATE_TAG="$(date +%Y%m%d_%H%M%S)"
DIST_DIR="${ROOT}/dist/release"
FRONT_DIST="${ROOT}/front/dist"
BACKEND_ZIP="${DIST_DIR}/devmind-ai-backend-${DATE_TAG}.zip"
FRONT_ZIP="${DIST_DIR}/devmind-ai-frontend-${DATE_TAG}.zip"

echo "==> 1/2 打包前端"
cd "${ROOT}/front"
npm ci
npm run build

echo "==> 2/2 打包后端 zip"
mkdir -p "${DIST_DIR}"
rm -f "${BACKEND_ZIP}" "${FRONT_ZIP}"

cd "${ROOT}/front/dist"
zip -r "${FRONT_ZIP}" .

cd "${ROOT}"
zip -r "${BACKEND_ZIP}" \
  backend base internal_kb_qa config.ini pyproject.toml uv.lock sql docker scripts locust_test.py \
  -x "**/__pycache__/*" "**/*.pyc" "**/.venv/*" "**/node_modules/*" "**/data/uploads/*" "**/logs/*" "**/.git/*" "**/internal_kb_qa/models/*"

echo ""
echo "打包完成："
echo "  前端: ${FRONT_ZIP}"
echo "  后端: ${BACKEND_ZIP}"
