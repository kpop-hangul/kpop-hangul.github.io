#!/bin/bash
set -e

# ==============================================================================
# Auto Blog Systemd Service Installer (User-level)
# ==============================================================================

SERVICE_DIR="${HOME}/.config/systemd/user"
mkdir -p "${SERVICE_DIR}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Read BLOG_ID from .env or blog.config.json
if [ -f "${ROOT_DIR}/.env" ]; then
    BLOG_ID=$(grep -E '^BLOG_ID=' "${ROOT_DIR}/.env" | cut -d '=' -f2 | tr -d ' "' || echo "auto-blog")
else
    BLOG_ID="auto-blog"
fi

SERVICE_NAME="auto-blog-${BLOG_ID}.service"
SERVICE_PATH="${SERVICE_DIR}/${SERVICE_NAME}"

echo "🔧 Registering systemd user service: ${SERVICE_NAME}..."

sed -e "s|{{INSTALL_DIR}}|${ROOT_DIR}|g" \
    -e "s|{{BLOG_ID}}|${BLOG_ID}|g" \
    -e "s|{{SITE_NAME}}|${BLOG_ID}|g" \
    "${SCRIPT_DIR}/systemd.service.template" > "${SERVICE_PATH}"

systemctl --user daemon-reload
systemctl --user enable "${SERVICE_NAME}"
systemctl --user restart "${SERVICE_NAME}"

echo "✅ [OK] ${SERVICE_NAME} 가 성공적으로 등록되고 시작되었습니다!"
echo "상태 확인 명령어: systemctl --user status ${SERVICE_NAME}"
echo "로그 확인 명령어: journalctl --user -u ${SERVICE_NAME} -f"
