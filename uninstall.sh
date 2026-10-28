#!/bin/bash
# Nexfiber — bongkar instalasi lokal (service, app dir, config). DB tidak dihapus otomatis.
# SEBELUM menghapus apa pun: config.ini dibackup dan DB di-pg_dump (wajib — bila
# pg_dump tidak tersedia atau dump gagal, uninstall dibatalkan) ke
# /var/backups/nexfiber, karena config berisi secret yang dibutuhkan untuk
# mendekripsi kredensial OLT di DB yang dipertahankan.
set -e
# File backup (dump DB, salinan config) hanya boleh dibaca pemilik + grup.
umask 027
RED='\033[1;31m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
if [ "$(id -u)" -ne 0 ]; then echo -e "${RED}Jalankan dengan root/sudo.${NC}"; exit 1; fi

read -rp "Hapus instalasi Nexfiber (service + /opt/nexfiber + /etc/nexfiber)? [y/N]: " CONFIRM
case "$CONFIRM" in y|Y|yes|YES) ;; *) echo "Dibatalkan."; exit 0;; esac

BACKUP_DIR="/var/backups/nexfiber"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
DB_NAME=""; DB_USER=""
if [ -f /etc/nexfiber/config.ini ]; then
    cp /etc/nexfiber/config.ini "$BACKUP_DIR/config.ini.$STAMP"
    chmod 640 "$BACKUP_DIR/config.ini.$STAMP"
    echo -e "${YELLOW}Backup config (berisi secret): ${BACKUP_DIR}/config.ini.${STAMP} — JANGAN hapus file ini bila DB dipertahankan.${NC}"
    DB_NAME="$(grep -E '^url[[:space:]]*=' /etc/nexfiber/config.ini | sed 's/.*\///; s/?.*//; s/#.*//')"
    DB_USER="$(grep -E '^url[[:space:]]*=' /etc/nexfiber/config.ini | sed 's/.*:\/\///; s/:.*//')"
fi
# pg_dump WAJIB (tidak ada flag untuk melewatinya): uninstall membatalkan
# bila pg_dump tidak tersedia, nama DB tidak terbaca, atau dump gagal — tidak
# lagi menghapus instalasi tanpa backup DB. Pengecualian yang disengaja: bila
# tidak ada config.ini sama sekali, tidak ada nama DB yang bisa dibaca; dalam
# hal itu tidak ada DB yang bisa di-backup dari config, dan uninstall tetap
# jalan (tidak ada yang bisa diselamatkan dari config yang sudah hilang).
if [ -f /etc/nexfiber/config.ini ]; then
    if ! command -v pg_dump &>/dev/null || [ -z "$DB_NAME" ]; then
        echo -e "${RED}pg_dump tidak tersedia / nama DB tidak terbaca — uninstall dibatalkan TANPA backup DB.${NC}"
        exit 1
    fi
    if ! sudo -u postgres pg_dump "$DB_NAME" > "$BACKUP_DIR/db-$DB_NAME-$STAMP.sql" 2>/dev/null; then
        echo -e "${RED}pg_dump gagal untuk ${DB_NAME} — uninstall dibatalkan TANPA backup DB.${NC}"
        exit 1
    fi
    chmod 640 "$BACKUP_DIR/db-$DB_NAME-$STAMP.sql"
    echo -e "${YELLOW}Backup DB: ${BACKUP_DIR}/db-${DB_NAME}-${STAMP}.sql${NC}"
fi

systemctl disable --now nexfiber-api nexfiber-worker 2>/dev/null || true
rm -f /etc/systemd/system/nexfiber-api.service /etc/systemd/system/nexfiber-worker.service
systemctl daemon-reload
rm -rf /opt/nexfiber /etc/nexfiber
echo -e "${GREEN}✔ Service dan folder app dihapus.${NC}"
echo -e "${YELLOW}Database PostgreSQL TIDAK dihapus otomatis. Hapus manual bila perlu:${NC}"
if [ -n "$DB_NAME" ] && [ -n "$DB_USER" ]; then
    echo "  sudo -u postgres psql -c 'DROP DATABASE ${DB_NAME};'"
    echo "  sudo -u postgres psql -c 'DROP ROLE ${DB_USER};'"
else
    echo "  sudo -u postgres psql -c 'DROP DATABASE nexfiber_db;'  (ganti dengan nama DB dari backup config bila berbeda)"
    echo "  sudo -u postgres psql -c 'DROP ROLE nexfiber_user;'  (ganti dengan user DB dari backup config bila berbeda)"
fi
