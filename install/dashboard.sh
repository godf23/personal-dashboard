#!/usr/bin/env bash
# Personal Dashboard — one-line installer
# Usage: bash -c "$(curl -fsSL https://raw.githubusercontent.com/Racoon/personal-dashboard/main/install/dashboard.sh)"

set -euo pipefail

REPO="${DASHBOARD_REPO:-Racoon/personal-dashboard}"
BRANCH="${DASHBOARD_BRANCH:-main}"
INSTALL_DIR="${DASHBOARD_DIR:-/opt/personal-dashboard}"
SERVICE_NAME="personal-dashboard"
DEFAULT_PORT=8080

YW='\033[33m'
GN='\033[1;92m'
RD='\033[01;31m'
BL='\033[36m'
CL='\033[m'
CM="${GN}✔${CL}"
CROSS="${RD}✖${CL}"

header() {
  clear
  cat <<'EOF'
  ____            _        _     ____            _     _
 |  _ \  ___  ___| |_ __ _| |   |  _ \  __ _ ___| |__ (_) __ _ _ __
 | | | |/ _ \/ __| __/ _` | |   | | | |/ _` / __| '_ \| |/ _` | '_ \
 | |_| |  __/\__ \ || (_| | |   | |_| | (_| \__ \ | | | | (_| | | | |
 |____/ \___||___/\__\__,_|_|   |____/ \__,_|___/_| |_|_|\__,_|_| |_|

EOF
}

msg_info() { echo -e "${BL}→${CL} ${YW}$1${CL}"; }
msg_ok()   { echo -e "${CM} ${GN}$1${CL}"; }
msg_err()  { echo -e "${CROSS} ${RD}$1${CL}"; }

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    msg_err "Run as root: sudo bash -c \"\$(curl -fsSL ...)\""
    exit 1
  fi
}

detect_os() {
  if [[ -f /etc/debian_version ]]; then
    OS="debian"
    PKG="apt-get install -y"
  elif [[ -f /etc/alpine-release ]]; then
    OS="alpine"
    PKG="apk add --no-cache"
  elif [[ -f /etc/redhat-release ]]; then
    OS="redhat"
    PKG="dnf install -y"
  else
    msg_err "Unsupported OS. Debian/Ubuntu, Alpine, or RHEL/Fedora required."
    exit 1
  fi
}

install_deps() {
  msg_info "Installing system packages"
  if [[ "$OS" == "debian" ]]; then
    apt-get update -qq
    $PKG git curl python3 python3-venv python3-pip build-essential
  elif [[ "$OS" == "alpine" ]]; then
    $PKG git curl python3 py3-pip py3-virtualenv build-base linux-headers
  else
    $PKG git curl python3 python3-pip gcc gcc-c++ make
  fi
  msg_ok "System packages installed"
}

get_ip() {
  local ip
  ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  [[ -z "$ip" ]] && ip="127.0.0.1"
  echo "$ip"
}

clone_or_update() {
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    msg_info "Updating existing install in $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch origin "$BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
  else
    msg_info "Cloning into $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
    git clone --depth 1 --branch "$BRANCH" "https://github.com/${REPO}.git" "$INSTALL_DIR"
  fi
  msg_ok "Source ready"
}

setup_python() {
  msg_info "Creating Python virtual environment"
  cd "$INSTALL_DIR"
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --upgrade pip -q
  pip install -r requirements.txt -q
  msg_ok "Python dependencies installed"
}

setup_env() {
  cd "$INSTALL_DIR"
  if [[ ! -f .env ]]; then
    cp .env.example .env
    msg_ok "Created .env from .env.example — edit $INSTALL_DIR/.env with your API keys"
  else
    msg_ok ".env already exists (unchanged)"
  fi
}

create_service() {
  local port="$1"
  local ip
  ip=$(get_ip)

  msg_info "Creating systemd service on port $port"
  cat >"/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Personal Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment=HOST=0.0.0.0
Environment=PORT=${port}
ExecStart=${INSTALL_DIR}/.venv/bin/python start.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"
  msg_ok "Service started"
  echo ""
  echo -e "${CM} ${GN}Dashboard is running at:${CL} ${BL}http://${ip}:${port}${CL}"
  echo -e "${YW}Edit API keys:${CL} ${INSTALL_DIR}/.env"
  echo -e "${YW}Logs:${CL} journalctl -u ${SERVICE_NAME} -f"
}

uninstall() {
  msg_info "Uninstalling Personal Dashboard"
  systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
  systemctl daemon-reload 2>/dev/null || true
  rm -rf "$INSTALL_DIR"
  msg_ok "Uninstalled"
  exit 0
}

main() {
  header
  need_root
  detect_os

  if [[ -d "$INSTALL_DIR" ]] && [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]; then
    echo -e "${YW}Personal Dashboard is already installed in ${INSTALL_DIR}${CL}"
    echo -n "Uninstall? (y/N): "
    read -r ans
    if [[ "${ans,,}" =~ ^(y|yes)$ ]]; then
      uninstall
    fi
    echo -n "Reinstall / update? (y/N): "
    read -r ans
    if [[ ! "${ans,,}" =~ ^(y|yes)$ ]]; then
      echo "Aborted."
      exit 0
    fi
  fi

  echo -n "Install directory (default: ${INSTALL_DIR}): "
  read -r dir_in
  [[ -n "$dir_in" ]] && INSTALL_DIR="$dir_in"

  echo -n "Port (default: ${DEFAULT_PORT}): "
  read -r port_in
  PORT="${port_in:-$DEFAULT_PORT}"

  echo -n "Proceed with install? (y/N): "
  read -r confirm
  if [[ ! "${confirm,,}" =~ ^(y|yes)$ ]]; then
    echo "Aborted."
    exit 0
  fi

  install_deps
  clone_or_update
  setup_python
  setup_env
  create_service "$PORT"
}

main "$@"
