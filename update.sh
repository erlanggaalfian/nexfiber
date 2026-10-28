#!/bin/bash
# Nexfiber — update rilis setelah git pull. Jalankan dari folder source.
# Urutan aman: hentikan service -> backup kode + config + DB -> rsync (dengan
# --delete supaya file sumber yang dihapus tidak tertinggal) -> dependency ->
# migrasi -> build -> start -> health check. Bila health check gagal, kode
# lama di-restore dan service di-restart; DB TIDAK di-rollback otomatis
# (restore dari pg_dump di bawah bila perlu).
set -e
# File backup (dump DB, salinan config) hanya boleh dibaca pemilik + grup.
umask 027

RED='\033[1;31m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; CYAN='\033[1;36m'; NC='\033[0m'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/nexfiber"
CONFIG_DIR="/etc/nexfiber"
BACKUP_DIR="/var/backups/nexfiber"
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
if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
    echo -e "${RED}Node.js/npm tidak ditemukan. Instal Node.js dulu, lalu jalankan lagi update.sh.${NC}"
    exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
APP_BACKUP="$BACKUP_DIR/app-$STAMP"
# Trap ERR: kegagalan apa pun setelah backup lengkap (pip/migrasi/build/start)
# harus mengembalikan service lama, bukan membiarkan service mati dengan kode
# setengah ter-update. BACKUP_DONE hanya diset setelah backup kode + config +
# dump DB selesai, supaya trap tidak me-restore dari backup yang belum lengkap
# (kegagalan selama backup sendiri berarti kode lama belum tersentuh, cukup
# restart service). Rollback konsisten yang dipilih: restore kode sumber dari
# backup; venv/dist TIDAK ikut di-backup (lihat docs/db-maintenance.md §4).
BACKUP_DONE=0
on_error() {
    echo -e "${RED}Update gagal di tengah jalan — mengembalikan service lama...${NC}"
    if [ "$BACKUP_DONE" = "1" ] && [ -d "$APP_BACKUP" ]; then
        rsync -a --delete --exclude 'venv/' --exclude 'node_modules/' --exclude 'dist/' --exclude '__pycache__/' \
            "$APP_BACKUP/" "$APP_DIR/" 2>/dev/null || true
        chown -R "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$APP_DIR" 2>/dev/null || true
        echo -e "${RED}Kode lama di-restore dari ${APP_BACKUP}. DB TIDAK di-rollback otomatis.${NC}"
    fi
    systemctl start nexfiber-api nexfiber-worker 2>/dev/null || true
}
trap on_error ERR
DB_NAME="$(grep -E '^url[[:space:]]*=' "$CONFIG_DIR/config.ini" | sed 's/.*\///; s/?.*//; s/#.*//')"
DB_DUMP="$BACKUP_DIR/db-$DB_NAME-$STAMP.sql"

echo -e "${CYAN}[0/5]${NC} Hentikan service + backup..."
systemctl stop nexfiber-api nexfiber-worker 2>/dev/null || true
mkdir -p "$BACKUP_DIR"
rsync -a --exclude 'venv/' --exclude 'node_modules/' --exclude 'dist/' --exclude '__pycache__/' \
    "$APP_DIR/" "$APP_BACKUP/"
cp "$CONFIG_DIR/config.ini" "$BACKUP_DIR/config.ini.$STAMP"
chmod 640 "$BACKUP_DIR/config.ini.$STAMP"
# pg_dump WAJIB: tidak ada flag operator untuk melewatinya, jadi bila pg_dump
# tidak tersedia atau nama DB tidak terbaca, update dibatalkan sebelum
# perubahan apa pun (service di-restart kembali di bawah).
if ! command -v pg_dump &>/dev/null || [ -z "$DB_NAME" ]; then
    echo -e "${RED}pg_dump tidak tersedia / nama DB tidak terbaca — update dibatalkan TANPA backup DB.${NC}"
    systemctl start nexfiber-api nexfiber-worker 2>/dev/null || true
    exit 1
fi
if ! sudo -u postgres pg_dump "$DB_NAME" > "$DB_DUMP" 2>/dev/null; then
    echo -e "${RED}pg_dump gagal untuk database ${DB_NAME} — update dibatalkan SEBELUM perubahan apa pun.${NC}"
    systemctl start nexfiber-api nexfiber-worker 2>/dev/null || true
    exit 1
fi
chmod 640 "$DB_DUMP"
echo -e "${YELLOW}Backup DB: ${DB_DUMP} (restore: sudo -u postgres psql ${DB_NAME} < ${DB_DUMP})${NC}"
BACKUP_DONE=1

echo -e "${CYAN}[1/5]${NC} Sinkronkan kode ke ${APP_DIR}..."
rsync -a --delete --exclude '.git/' --exclude 'venv/' --exclude 'node_modules/' --exclude '__pycache__/' --exclude 'dist/' \
    "$SCRIPT_DIR/" "$APP_DIR/"
chown -R "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$APP_DIR"

echo -e "${CYAN}[2/5]${NC} Update dependency Python..."
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q

echo -e "${CYAN}[3/5]${NC} Migrasi database (alembic upgrade head)..."
( cd "$APP_DIR/backend" && NEXFIBER_CONFIG="$CONFIG_DIR/config.ini" "$APP_DIR/venv/bin/alembic" upgrade head )

echo -e "${CYAN}[4/5]${NC} Build ulang frontend..."
( cd "$APP_DIR/frontend" && npm ci -q && npm run build )

echo -e "${CYAN}[5/5]${NC} Start service..."
systemctl start nexfiber-api nexfiber-worker

HTTP_CODE="000"
for _ in $(seq 1 30); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "http://127.0.0.1:${APP_PORT}/healthz" 2>/dev/null || echo "000")
    [ "$HTTP_CODE" = "200" ] && break
    sleep 2
done
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✔ Update selesai, API OK (HTTP ${HTTP_CODE})${NC}"
else
    echo -e "${RED}⚠ API tidak sehat setelah update (HTTP ${HTTP_CODE}) — rollback kode lama...${NC}"
    rsync -a --delete --exclude 'venv/' --exclude 'node_modules/' --exclude 'dist/' --exclude '__pycache__/' \
        "$APP_BACKUP/" "$APP_DIR/"
    chown -R "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$APP_DIR"
    systemctl restart nexfiber-api nexfiber-worker 2>/dev/null || true
    echo -e "${RED}Kode lama di-restore dari ${APP_BACKUP}. DB TIDAK di-rollback otomatis; restore DB dari ${DB_DUMP} bila migrasi sudah jalan.${NC}"
    exit 1
fi
