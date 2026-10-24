#!/bin/bash
# Nexfiber — bongkar instalasi lokal (service, app dir, config). DB tidak dihapus otomatis.
set -e
RED='\033[1;31m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
if [ "$(id -u)" -ne 0 ]; then echo -e "${RED}Jalankan dengan root/sudo.${NC}"; exit 1; fi

read -rp "Hapus instalasi Nexfiber (service + /opt/nexfiber + /etc/nexfiber)? [y/N]: " CONFIRM
case "$CONFIRM" in y|Y|yes|YES) ;; *) echo "Dibatalkan."; exit 0;; esac

systemctl disable --now nexfiber-api nexfiber-worker 2>/dev/null || true
rm -f /etc/systemd/system/nexfiber-api.service /etc/systemd/system/nexfiber-worker.service
systemctl daemon-reload
rm -rf /opt/nexfiber /etc/nexfiber
echo -e "${GREEN}✔ Service dan folder app dihapus.${NC}"
echo -e "${YELLOW}Database PostgreSQL TIDAK dihapus otomatis. Hapus manual bila perlu:${NC}"
echo "  sudo -u postgres psql -c 'DROP DATABASE nexfiber_db;'"
echo "  sudo -u postgres psql -c 'DROP ROLE nexfiber_user;'"
