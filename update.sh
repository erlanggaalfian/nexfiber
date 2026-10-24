#!/bin/bash
# Nexfiber — update rilis setelah git pull. Jalankan dari folder source.
set -e

RED='\033[1;31m'; GREEN='\033[1;32m'; CYAN='\033[1;36m'; NC='\033[0m'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/nexfiber"
CONFIG_DIR="/etc/nexfiber"
APP_SYSTEM_USER="nexfiber"
APP_PORT="8088"

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Jalankan dengan root/sudo: sudo bash update.sh${NC}"
    exit 1
fi
if [ ! -d "$APP_DIR" ] || [ ! -f "$CONFIG_DIR/config.ini" ]; then
    echo -e "${RED}${APP_DIR} atau ${CONFIG_DIR}/config.ini tidak ada. Jalankan install.sh dulu.${NC}"
    exit 1
fi

echo -e "${CYAN}[1/5]${NC} Sinkronkan kode ke ${APP_DIR}..."
rsync -a --exclude '.git/' --exclude 'venv/' --exclude 'node_modules/' --exclude '__pycache__/' --exclude 'dist/' \
    "$SCRIPT_DIR/" "$APP_DIR/"
chown -R "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$APP_DIR"

echo -e "${CYAN}[2/5]${NC} Update dependency Python..."
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q

echo -e "${CYAN}[3/5]${NC} Migrasi database (alembic upgrade head)..."
( cd "$APP_DIR/backend" && NEXFIBER_CONFIG="$CONFIG_DIR/config.ini" "$APP_DIR/venv/bin/alembic" upgrade head )

echo -e "${CYAN}[4/5]${NC} Build ulang frontend..."
( cd "$APP_DIR/frontend" && npm ci -q && npm run build )

echo -e "${CYAN}[5/5]${NC} Restart service..."
systemctl restart nexfiber-api nexfiber-worker

sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "http://127.0.0.1:${APP_PORT}/healthz" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✔ Update selesai, API OK (HTTP ${HTTP_CODE})${NC}"
else
    echo -e "${RED}⚠ API tidak sehat setelah update (HTTP ${HTTP_CODE}) — cek: journalctl -u nexfiber-api -n 50${NC}"
    exit 1
fi
