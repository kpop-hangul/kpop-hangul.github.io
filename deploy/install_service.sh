#!/bin/bash
set -e

# ==============================================================================
# K-Pop Hangul Systemd User Service & Timer Installer
# ==============================================================================

SERVICE_DIR="${HOME}/.config/systemd/user"
mkdir -p "${SERVICE_DIR}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PIPELINE_SERVICE="auto-blog-kpop-pipeline.service"
PIPELINE_TIMER="auto-blog-kpop-pipeline.timer"

echo "🔧 Installing K-Pop Hangul Daily Automation Pipeline to ${SERVICE_DIR}..."

cp "${SCRIPT_DIR}/${PIPELINE_SERVICE}" "${SERVICE_DIR}/${PIPELINE_SERVICE}"
cp "${SCRIPT_DIR}/${PIPELINE_TIMER}" "${SERVICE_DIR}/${PIPELINE_TIMER}"

systemctl --user daemon-reload
systemctl --user enable "${PIPELINE_TIMER}"
systemctl --user restart "${PIPELINE_TIMER}"

echo "✅ [OK] ${PIPELINE_TIMER} registered and started!"
echo "Timer status check: systemctl --user list-timers --all | grep kpop"
echo "Manual trigger command: systemctl --user start ${PIPELINE_SERVICE}"
echo "Log check command: journalctl --user -u ${PIPELINE_SERVICE} -f"

