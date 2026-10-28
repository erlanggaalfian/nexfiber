#!/bin/bash
# Nexfiber — instalasi lokal di server ini, satu port, tanpa Docker/Caddy.
# PERINGATAN: akses masih HTTP tanpa TLS (uvicorn 0.0.0.0:8088). Installer ini
# TIDAK mengklaim HTTPS dan TIDAK mengonfigurasi Caddy/firewall — pakai hanya
# di LAN tepercaya, jangan ekspos port 8088 ke internet. Keputusan Caddy vs
# LAN-only masih butuh keputusan pemilik (dokumen saling bertentangan:
# AGENTS.md/PRD menyebut Caddy+HTTPS, DECISIONS.md menyebut tanpa Caddy).
#
# Usage (dari folder source project, hasil git clone):
#   chmod +x install.sh
#   sudo bash install.sh

set -e

RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
CYAN='\033[1;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_SYSTEM_USER="nexfiber"
LOG_FILE="/var/log/nexfiber_install.log"
APP_DIR="/opt/nexfiber"
CONFIG_DIR="/etc/nexfiber"
BACKUP_DIR="/var/backups/nexfiber"
LOGDIR="/var/log/nexfiber"
APP_PORT="8088"
PYTHON_BIN="python3"

error_exit() {
    echo ""
    echo -e "${RED}==================================================${NC}"
    echo -e "${RED} ❌ INSTALLASI GAGAL${NC}"
    echo -e "${RED}==================================================${NC}"
    if [ -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}Detail error (20 baris terakhir):${NC}"
        tail -20 "$LOG_FILE"
        echo -e "${YELLOW}Full log:${NC} $LOG_FILE"
    fi
    exit 1
}
trap error_exit ERR

log() {
    echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $1"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}
success() { echo -e "${GREEN}✔ $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $1${NC}"; }

psql_root() { sudo -u postgres psql -v ON_ERROR_STOP=1 -tAc "$1" 2>>"$LOG_FILE"; }
db_role_exists() { [ "$(psql_root "SELECT 1 FROM pg_roles WHERE rolname='$1'")" = "1" ]; }
db_exists() { [ "$(psql_root "SELECT 1 FROM pg_database WHERE datname='$1'")" = "1" ]; }

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Installer harus dijalankan dengan root/sudo.${NC}"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/backend/requirements.txt" ] || [ ! -f "$SCRIPT_DIR/frontend/package.json" ]; then
    echo -e "${RED}Jalankan script dari root folder project (ada backend/requirements.txt dan frontend/package.json).${NC}"
    exit 1
fi

# Node/npm wajib untuk build frontend — gagal jelas di awal, bukan di langkah [6].
if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
    echo -e "${RED}Node.js/npm tidak ditemukan. Instal Node.js dulu (mis. dari repo OS / nodesource), lalu jalankan lagi install.sh.${NC}"
    exit 1
fi

if ss -tln 2>/dev/null | grep -q ":${APP_PORT} "; then
    echo -e "${RED}Port ${APP_PORT} sudah dipakai proses lain. Edit APP_PORT di install.sh lalu coba lagi.${NC}"
    exit 1
fi

echo -e "${GREEN}Nexfiber Installer — install lokal di server ini (port ${APP_PORT}, tanpa Docker)${NC}"
echo ""

# =========================================================
# [1] KONFIGURASI DATABASE
# =========================================================
echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE} [1/8] Konfigurasi Database${NC}"
echo -e "${BLUE}==================================================${NC}"

read -rp "Database Name [nexfiber_db]: " DB_NAME
DB_NAME=${DB_NAME:-nexfiber_db}

read -rp "Database User [nexfiber_user]: " DB_USER
DB_USER=${DB_USER:-nexfiber_user}

read -rsp "Password user database (kosong = auto generate): " DB_PASS
echo ""
if [ -z "$DB_PASS" ]; then
    DB_PASS="$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)"
    echo -e "${YELLOW}Password database auto-generated (tersimpan di config.ini, tidak dicetak di akhir).${NC}"
fi
# Validasi nama DB/user (dipakai mentah di SQL) + escape password untuk SQL dan URL.
# Nama yang tidak cocok pola ini ditolak, bukan di-escape diam-diam.
if ! [[ "$DB_NAME" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || ! [[ "$DB_USER" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
    echo -e "${RED}Nama database/user hanya boleh huruf, angka, dan underscore, diawali huruf/underscore.${NC}"
    exit 1
fi
DB_PASS_SQL="${DB_PASS//\'/\'\'}"
DB_PASS_URL="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$DB_PASS")"
# Secret lama DIPERTAHANKAN bila config sudah ada: menimpa app_secret_key membuat
# semua kredensial OLT terenkripsi di DB lama tidak bisa dibuka lagi.
# Config BARU memakai dua nilai acak terpisah (app untuk Fernet, jwt untuk token);
# config lama yang hanya punya satu secret_key tetap jalan karena config.py
# memakai secret_key sebagai fallback untuk kunci yang tidak ditulis.
mkdir -p "$BACKUP_DIR"
OLD_SECRET=""; OLD_APP=""; OLD_JWT=""
if [ -f "$CONFIG_DIR/config.ini" ]; then
    cp "$CONFIG_DIR/config.ini" "$BACKUP_DIR/config.ini.$(date +%Y%m%d-%H%M%S)"
    chmod 640 "$BACKUP_DIR"/config.ini.* 2>/dev/null || true
    OLD_SECRET="$(grep -E '^secret_key[[:space:]]*=' "$CONFIG_DIR/config.ini" | sed 's/^[^=]*=[[:space:]]*//' | tr -d '[:space:]')"
    OLD_APP="$(grep -E '^app_secret_key[[:space:]]*=' "$CONFIG_DIR/config.ini" | sed 's/^[^=]*=[[:space:]]*//' | tr -d '[:space:]')"
    OLD_JWT="$(grep -E '^jwt_secret_key[[:space:]]*=' "$CONFIG_DIR/config.ini" | sed 's/^[^=]*=[[:space:]]*//' | tr -d '[:space:]')"
    echo -e "${YELLOW}config.ini lama dibackup ke ${BACKUP_DIR} dan secret dipertahankan.${NC}"
fi
APP_SECRET_KEY="${OLD_APP:-${OLD_SECRET:-$(openssl rand -hex 32)}}"
JWT_SECRET_KEY="${OLD_JWT:-${OLD_SECRET:-$(openssl rand -hex 32)}}"
SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
SERVER_IP="${SERVER_IP:-127.0.0.1}"

echo ""
echo -e "Install ke : ${CYAN}${APP_DIR}${NC}"
echo -e "Database   : ${CYAN}${DB_NAME}${NC} (user: ${CYAN}${DB_USER}${NC})"
echo -e "Akses      : ${CYAN}http://${SERVER_IP}:${APP_PORT}${NC}"
echo ""
read -rp "Lanjutkan instalasi? [y/N]: " CONFIRM
case "$CONFIRM" in
    y|Y|yes|YES) ;;
    *) echo -e "${YELLOW}Instalasi dibatalkan.${NC}"; exit 0 ;;
esac
echo ""

# =========================================================
# [2] PAKET SISTEM (pakai yang tersedia di repo Debian — tidak nambah apt source baru)
# =========================================================
log "[2/8] Install paket sistem (PostgreSQL, Python venv, dll)..."
apt-get update -y >> "$LOG_FILE" 2>&1
apt-get install -y postgresql postgresql-client python3-venv python3-pip git curl openssl snmp >> "$LOG_FILE" 2>&1
success "PostgreSQL + Python venv terpasang"
success "Node.js $(node -v) + npm $(npm -v) terpasang"
echo ""

# =========================================================
# [3] USER & DIREKTORI
# =========================================================
log "[3/8] Setup user sistem & direktori..."
if ! id "$APP_SYSTEM_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_SYSTEM_USER" >> "$LOG_FILE" 2>&1
fi
mkdir -p "$APP_DIR" "$CONFIG_DIR" "$BACKUP_DIR" "$LOGDIR"
if command -v rsync &>/dev/null; then
    rsync -a --exclude '.git/' --exclude 'venv/' --exclude 'node_modules/' --exclude '__pycache__/' \
        "$SCRIPT_DIR/" "$APP_DIR/" >> "$LOG_FILE" 2>&1
else
    cp -a "$SCRIPT_DIR"/. "$APP_DIR"/ 2>>"$LOG_FILE"
fi
chown -R "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$APP_DIR" "$LOGDIR" "$BACKUP_DIR" "$CONFIG_DIR"
chmod 750 "$CONFIG_DIR"
success "Direktori siap: ${APP_DIR}, ${CONFIG_DIR}, ${BACKUP_DIR}"
echo ""

# =========================================================
# [4] DATABASE
# =========================================================
log "[4/8] Setup database PostgreSQL..."
systemctl enable --now postgresql >> "$LOG_FILE" 2>&1

if ! db_role_exists "$DB_USER"; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS_SQL}';" >> "$LOG_FILE" 2>&1
else
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER ROLE ${DB_USER} PASSWORD '${DB_PASS_SQL}';" >> "$LOG_FILE" 2>&1
    warn "Role ${DB_USER} sudah ada — password diperbarui"
fi

if ! db_exists "$DB_NAME"; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" >> "$LOG_FILE" 2>&1
else
    warn "Database ${DB_NAME} sudah ada — dilewati"
fi
success "Database ${DB_NAME} siap (user: ${DB_USER})"
echo ""

# =========================================================
# [5] CONFIG, VENV, MIGRASI
# =========================================================
log "[5/8] Tulis config, siapkan venv, migrasi..."
# Backup config lama sekali lagi tepat sebelum ditimpa (backup di awal juga ada).
if [ -f "$CONFIG_DIR/config.ini" ]; then
    cp "$CONFIG_DIR/config.ini" "$BACKUP_DIR/config.ini.$(date +%Y%m%d-%H%M%S).pre-write"
    chmod 640 "$BACKUP_DIR"/config.ini.*.pre-write 2>/dev/null || true
fi
cat > "$CONFIG_DIR/config.ini" << EOF2
[database]
url = postgresql+asyncpg://${DB_USER}:${DB_PASS_URL}@localhost:5432/${DB_NAME}

[app]
app_secret_key = ${APP_SECRET_KEY}
jwt_secret_key = ${JWT_SECRET_KEY}
EOF2
chown "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$CONFIG_DIR/config.ini"
chmod 640 "$CONFIG_DIR/config.ini"

"$PYTHON_BIN" -m venv "$APP_DIR/venv" >> "$LOG_FILE" 2>&1
"$APP_DIR/venv/bin/pip" install --upgrade pip >> "$LOG_FILE" 2>&1
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" >> "$LOG_FILE" 2>&1
success "Python venv siap"

( cd "$APP_DIR/backend" && \
  NEXFIBER_CONFIG="$CONFIG_DIR/config.ini" "$APP_DIR/venv/bin/alembic" upgrade head >> "$LOG_FILE" 2>&1 )
success "Migrasi database selesai (alembic upgrade head)"
echo ""

# =========================================================
# [6] BUILD FRONTEND
# =========================================================
log "[6/8] Build frontend..."
( cd "$APP_DIR/frontend" && npm ci >> "$LOG_FILE" 2>&1 && npm run build >> "$LOG_FILE" 2>&1 )
success "Frontend ter-build (${APP_DIR}/frontend/dist, disajikan langsung oleh API)"
echo ""

# =========================================================
# [7] SYSTEMD UNITS
# =========================================================
log "[7/8] Tulis systemd unit (API + worker)..."
cat > /etc/systemd/system/nexfiber-api.service << EOF3
[Unit]
Description=Nexfiber API (FastAPI/Uvicorn, sekaligus sajikan frontend)
After=network.target postgresql.service

[Service]
User=${APP_SYSTEM_USER}
Group=${APP_SYSTEM_USER}
WorkingDirectory=${APP_DIR}/backend
Environment=NEXFIBER_CONFIG=${CONFIG_DIR}/config.ini
ExecStart=${APP_DIR}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF3

cat > /etc/systemd/system/nexfiber-worker.service << EOF4
[Unit]
Description=Nexfiber Background Worker (job table poller)
After=network.target postgresql.service nexfiber-api.service

[Service]
User=${APP_SYSTEM_USER}
Group=${APP_SYSTEM_USER}
WorkingDirectory=${APP_DIR}/backend
Environment=NEXFIBER_CONFIG=${CONFIG_DIR}/config.ini
ExecStart=${APP_DIR}/venv/bin/python -m app.worker
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF4

systemctl daemon-reload
systemctl enable --now nexfiber-api.service nexfiber-worker.service >> "$LOG_FILE" 2>&1
success "systemd unit nexfiber-api & nexfiber-worker aktif"
echo ""

# =========================================================
# [8] HEALTH CHECK & RINGKASAN
# =========================================================
log "[8/8] Verifikasi instalasi..."
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "http://127.0.0.1:${APP_PORT}/healthz" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    success "Verifikasi API OK (HTTP ${HTTP_CODE} — http://127.0.0.1:${APP_PORT}/healthz)"
else
    echo -e "${RED}Verifikasi API gagal (HTTP ${HTTP_CODE}) — instalasi TIDAK diklaim berhasil. Cek: journalctl -u nexfiber-api -n 50${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN} ✅ NEXFIBER BERHASIL DIINSTALL${NC}"
echo -e "${GREEN}==================================================${NC}"
echo ""
echo -e "${CYAN}URL:${NC} http://${SERVER_IP}:${APP_PORT}/"
echo ""
echo -e "${CYAN}Database:${NC}"
echo "  Nama     : ${DB_NAME}"
echo "  User     : ${DB_USER}"
echo "  Password : (tidak dicetak — tersimpan di ${CONFIG_DIR}/config.ini, izin 640)"
echo ""
echo -e "${YELLOW}PERINGATAN:${NC} Akses masih HTTP tanpa TLS, hanya untuk LAN tepercaya. Jangan ekspos port ${APP_PORT} ke internet."
echo -e "${CYAN}Service:${NC}"
echo "  systemctl status nexfiber-api"
echo "  systemctl status nexfiber-worker"
echo ""
echo -e "${CYAN}Log instalasi:${NC} ${LOG_FILE}"
echo ""
echo -e "${YELLOW}Langkah berikutnya:${NC}"
echo "  1. Buka URL di browser, buat akun Superadmin di halaman Setup (muncul otomatis saat belum ada user)"
echo "  2. Untuk rilis berikutnya (setelah git pull): bash update.sh"
echo ""
