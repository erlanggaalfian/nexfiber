#!/bin/bash
# Nexfiber — instalasi server lengkap (konsep & gaya sama dengan install.sh NetBackup)
#
# Usage (dari folder source project, hasil git clone):
#   chmod +x install.sh
#   sudo bash install.sh
#
# Script akan:
#   - Install paket sistem (Python 3.12, PostgreSQL 18, Node.js, Caddy, …)
#   - Buat user sistem, direktori app, venv, build frontend
#   - Buat database + user + migrasi awal (Alembic)
#   - systemd unit (API + worker) + Caddy reverse-proxy & HTTPS
#   - Verifikasi web (health check) dan ringkasan kredensial di akhir

set -e

# =========================================================
# COLOR & PATH
# =========================================================

RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
CYAN='\033[1;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/VERSION" ]; then
    APP_VERSION="$(tr -d '\r\n' < "$SCRIPT_DIR/VERSION" | head -n1)"
else
    APP_VERSION="1.0.0"
fi

APP_SYSTEM_USER="nexfiber"
LOG_FILE="/var/log/nexfiber_install.log"

# =========================================================
# HELPERS
# =========================================================

error_exit() {
    echo ""
    echo -e "${RED}==================================================${NC}"
    echo -e "${RED} ❌ INSTALLASI GAGAL${NC}"
    echo -e "${RED}==================================================${NC}"
    echo ""
    if [ -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}Detail error (20 baris terakhir):${NC}"
        tail -20 "$LOG_FILE"
        echo ""
        echo -e "${YELLOW}Full log:${NC} $LOG_FILE"
    fi
    echo ""
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

slugify() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9.-]//g'
}

psql_root() {
    sudo -u postgres psql -v ON_ERROR_STOP=1 -tAc "$1" 2>>"$LOG_FILE"
}

db_role_exists() {
    [ "$(psql_root "SELECT 1 FROM pg_roles WHERE rolname='$1'")" = "1" ]
}

db_exists() {
    [ "$(psql_root "SELECT 1 FROM pg_database WHERE datname='$1'")" = "1" ]
}

# =========================================================
# ROOT CHECK & BANNER
# =========================================================

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Installer harus dijalankan dengan root/sudo.${NC}"
    echo -e "Contoh: ${GREEN}sudo bash install.sh${NC}"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/backend/requirements.txt" ] || [ ! -f "$SCRIPT_DIR/frontend/package.json" ]; then
    echo -e "${RED}Jalankan script dari root folder project (ada backend/requirements.txt dan frontend/package.json).${NC}"
    exit 1
fi

clear
echo -e "${BLUE}"
cat << 'EOF'

  ___  _   _____     _
 / _ \| | |_   _|   / \   ___  _ __
| | | | |   | |    / _ \ / _ \| '_ \
| |_| | |___| |   / ___ \ |_) | |_) |
 \___/|_____|_|  /_/   \_\__/| .__/
    OLT/ONU Management       |_|

EOF
echo -e "${NC}"
echo -e "${GREEN}Nexfiber Server Installer${NC}"
echo -e "${YELLOW}Debian 12 / Ubuntu 24.04 — Python 3.12 + FastAPI + PostgreSQL 18${NC}"
echo -e "${CYAN}Versi: v${APP_VERSION}${NC}"
echo -e "${CYAN}Source: ${SCRIPT_DIR}${NC}"
echo ""

# =========================================================
# [1] OS CHECK
# =========================================================

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE} [1/10] Deteksi Sistem Operasi${NC}"
echo -e "${BLUE}==================================================${NC}"

. /etc/os-release
case "${ID}-${VERSION_ID}" in
    debian-12*|debian-13*|ubuntu-24.*)
        success "OS didukung: ${PRETTY_NAME}"
        ;;
    *)
        echo -e "${RED}OS tidak didukung: ${PRETTY_NAME:-unknown}. Target: Debian 12/13 atau Ubuntu 24.04.${NC}"
        exit 1
        ;;
esac
echo ""

# =========================================================
# [2] KONFIGURASI DOMAIN / HTTPS
# =========================================================

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE} [2/10] Konfigurasi Domain & HTTPS${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "${YELLOW}Caddy mengurus HTTPS otomatis via Let's Encrypt begitu domain mengarah ke server ini.${NC}"
echo -e "${YELLOW}Isi IP server (tanpa domain) jika belum punya domain — Caddy akan jalan HTTP saja.${NC}"
echo ""

DEFAULT_DOMAIN="nexfiber.local"
read -rp "Domain / hostname [${DEFAULT_DOMAIN}]: " SERVER_NAME
SERVER_NAME=${SERVER_NAME:-$DEFAULT_DOMAIN}

APP_DIR="/opt/nexfiber"
CONFIG_DIR="/etc/nexfiber"
BACKUP_DIR="/var/backups/nexfiber"
LOGDIR="/var/log/nexfiber"

echo ""

# =========================================================
# [3] KONFIGURASI DATABASE
# =========================================================

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE} [3/10] Konfigurasi Database${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "${YELLOW}(Tekan Enter untuk nilai default)${NC}"
echo ""

read -rp "Database Name [nexfiber_db]: " DB_NAME
DB_NAME=${DB_NAME:-nexfiber_db}

read -rp "Database User [nexfiber_user]: " DB_USER
DB_USER=${DB_USER:-nexfiber_user}

read -rsp "Password user database (kosong = auto generate): " DB_PASS
echo ""
if [ -z "$DB_PASS" ]; then
    DB_PASS="$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)"
    echo -e "${YELLOW}Password database auto-generated.${NC}"
fi

SECRET_KEY="$(openssl rand -hex 32)"

echo ""
echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN} Memulai instalasi...${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "Domain     : ${CYAN}${SERVER_NAME}${NC}"
echo -e "Install ke : ${CYAN}${APP_DIR}${NC}"
echo -e "Database   : ${CYAN}${DB_NAME}${NC} (user: ${CYAN}${DB_USER}${NC})"
echo ""

read -rp "Lanjutkan instalasi? [y/N]: " CONFIRM
case "$CONFIRM" in
    y|Y|yes|YES) ;;
    *) echo -e "${YELLOW}Instalasi dibatalkan.${NC}"; exit 0 ;;
esac
echo ""

# =========================================================
# [4] PAKET SISTEM
# =========================================================

log "[4/10] Update repository & install paket sistem..."

apt-get update -y >> "$LOG_FILE" 2>&1

# PostgreSQL 18 dari repo resmi PGDG (Debian/Ubuntu stable belum selalu punya 18)
if ! command -v psql &>/dev/null || ! psql --version | grep -q " 18"; then
    install -d /usr/share/postgresql-common/pgdg
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc >> "$LOG_FILE" 2>&1
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list
    apt-get update -y >> "$LOG_FILE" 2>&1
fi

apt-get install -y \
    postgresql-18 postgresql-client-18 \
    python3.12 python3.12-venv python3-pip \
    git curl openssl snmp \
    >> "$LOG_FILE" 2>&1
success "Paket sistem (PostgreSQL 18, Python 3.12, git, snmp) terpasang"

# Node.js (NodeSource) — untuk build frontend
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >> "$LOG_FILE" 2>&1
    apt-get install -y nodejs >> "$LOG_FILE" 2>&1
fi
success "Node.js $(node -v 2>/dev/null) terpasang"

# Caddy (repo resmi)
if ! command -v caddy &>/dev/null; then
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https >> "$LOG_FILE" 2>&1
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
        gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg >> "$LOG_FILE" 2>&1
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list 2>>"$LOG_FILE"
    apt-get update -y >> "$LOG_FILE" 2>&1
    apt-get install -y caddy >> "$LOG_FILE" 2>&1
fi
success "Caddy terpasang"

echo ""

# =========================================================
# [5] USER & DIREKTORI
# =========================================================

log "[5/10] Setup user sistem & direktori..."

if ! id "$APP_SYSTEM_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_SYSTEM_USER" >> "$LOG_FILE" 2>&1
fi

mkdir -p "$APP_DIR" "$CONFIG_DIR" "$BACKUP_DIR" "$LOGDIR"

# Salin source ke APP_DIR (idempoten, exclude state yang tidak boleh ikut)
if command -v rsync &>/dev/null; then
    rsync -a --exclude '.git/' --exclude 'venv/' --exclude 'node_modules/' --exclude '__pycache__/' \
        "$SCRIPT_DIR/" "$APP_DIR/" >> "$LOG_FILE" 2>&1
else
    cp -a "$SCRIPT_DIR"/. "$APP_DIR"/ 2>>"$LOG_FILE"
fi

chown -R "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$APP_DIR" "$LOGDIR" "$BACKUP_DIR"
chmod 750 "$CONFIG_DIR"
success "Direktori siap: ${APP_DIR}, ${CONFIG_DIR}, ${BACKUP_DIR}"

echo ""

# =========================================================
# [6] DATABASE
# =========================================================

log "[6/10] Setup database PostgreSQL..."

systemctl enable --now postgresql >> "$LOG_FILE" 2>&1

if ! db_role_exists "$DB_USER"; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
        "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';" >> "$LOG_FILE" 2>&1
else
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
        "ALTER ROLE ${DB_USER} PASSWORD '${DB_PASS}';" >> "$LOG_FILE" 2>&1
    warn "Role ${DB_USER} sudah ada — password diperbarui"
fi

if ! db_exists "$DB_NAME"; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
        "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" >> "$LOG_FILE" 2>&1
else
    warn "Database ${DB_NAME} sudah ada — dilewati"
fi
success "Database ${DB_NAME} siap (user: ${DB_USER})"

echo ""

# =========================================================
# [7] CONFIG, VENV, BUILD, MIGRASI
# =========================================================

log "[7/10] Tulis config, siapkan venv, build frontend, migrasi..."

cat > "$CONFIG_DIR/config.ini" << EOF2
[database]
url = postgresql+asyncpg://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}

[app]
secret_key = ${SECRET_KEY}
domain = ${SERVER_NAME}
EOF2
chown "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$CONFIG_DIR/config.ini"
chmod 640 "$CONFIG_DIR/config.ini"

python3.12 -m venv "$APP_DIR/venv" >> "$LOG_FILE" 2>&1
"$APP_DIR/venv/bin/pip" install --upgrade pip >> "$LOG_FILE" 2>&1
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" >> "$LOG_FILE" 2>&1
success "Python venv siap"

( cd "$APP_DIR/frontend" && npm ci >> "$LOG_FILE" 2>&1 && npm run build >> "$LOG_FILE" 2>&1 )
success "Frontend ter-build"

( cd "$APP_DIR/backend" && \
  NEXFIBER_CONFIG="$CONFIG_DIR/config.ini" "$APP_DIR/venv/bin/alembic" upgrade head >> "$LOG_FILE" 2>&1 )
success "Migrasi database selesai (alembic upgrade head)"

echo ""

# =========================================================
# [8] SYSTEMD UNITS
# =========================================================

log "[8/10] Tulis systemd unit (API + worker)..."

cat > /etc/systemd/system/nexfiber-api.service << EOF3
[Unit]
Description=Nexfiber API (FastAPI/Uvicorn)
After=network.target postgresql.service

[Service]
User=${APP_SYSTEM_USER}
Group=${APP_SYSTEM_USER}
WorkingDirectory=${APP_DIR}/backend
Environment=NEXFIBER_CONFIG=${CONFIG_DIR}/config.ini
ExecStart=${APP_DIR}/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
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
# [9] CADDY (REVERSE PROXY + HTTPS)
# =========================================================

log "[9/10] Konfigurasi Caddy..."

cat > /etc/caddy/Caddyfile << EOF5
${SERVER_NAME} {
    root * ${APP_DIR}/frontend/dist
    encode gzip
    file_server

    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    handle /healthz {
        reverse_proxy 127.0.0.1:8000
    }

    try_files {path} /index.html
}
EOF5

systemctl enable --now caddy >> "$LOG_FILE" 2>&1
systemctl reload caddy >> "$LOG_FILE" 2>&1
success "Caddy terkonfigurasi untuk ${SERVER_NAME} (HTTPS otomatis bila domain publik)"

echo ""

# =========================================================
# [10] HEALTH CHECK & RINGKASAN
# =========================================================

log "[10/10] Verifikasi instalasi..."

sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "http://127.0.0.1:8000/healthz" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    success "Verifikasi API OK (HTTP ${HTTP_CODE} — http://127.0.0.1:8000/healthz)"
else
    warn "Verifikasi API gagal (HTTP ${HTTP_CODE}) — cek: journalctl -u nexfiber-api -n 50"
fi

echo ""
echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN} ✅ NEXFIBER BERHASIL DIINSTALL${NC}"
echo -e "${GREEN}==================================================${NC}"
echo ""
echo -e "${CYAN}URL:${NC} http://${SERVER_NAME}/ (HTTPS otomatis jika domain publik mengarah ke server ini)"
echo ""
echo -e "${CYAN}Instalasi:${NC}"
echo "  Versi   : v${APP_VERSION}"
echo "  Domain  : ${SERVER_NAME}"
echo "  Folder  : ${APP_DIR}"
echo "  Config  : ${CONFIG_DIR}/config.ini"
echo ""
echo -e "${CYAN}Database:${NC}"
echo "  Nama     : ${DB_NAME}"
echo "  User     : ${DB_USER}"
echo "  Password : ${DB_PASS}"
echo ""
echo -e "${CYAN}Service:${NC}"
echo "  systemctl status nexfiber-api"
echo "  systemctl status nexfiber-worker"
echo ""
echo -e "${CYAN}Log instalasi:${NC} ${LOG_FILE}"
echo ""
echo -e "${YELLOW}Langkah berikutnya:${NC}"
echo "  1. Buka URL di browser, buat akun Superadmin di halaman Setup (muncul otomatis saat belum ada user)"
echo "  2. Untuk rilis berikutnya pakai: bash update.sh"
echo "  3. Untuk bongkar server: bash uninstall.sh"
echo ""
echo -e "${GREEN}Nexfiber siap digunakan.${NC}"
echo ""
