#!/usr/bin/env bash
# MeshcoreStation setup and manual GitHub update menu. Run as the account that owns the application.
set -Eeuo pipefail
umask 077
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
service=meshcorestation.service
skip_apt=0
mode=menu
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
ask() { read -r -p "$1" "$2" || fail 'Input closed; no further action taken.'; }
for arg in "$@"; do
    case "$arg" in
        --skip-apt) skip_apt=1 ;;
        --install) mode=install ;;
        --update) mode=update ;;
        --apply-update) mode=apply_update ;;
        --uninstall) mode=uninstall ;;
        --help|-h) echo 'Usage: bash install.sh [--skip-apt] [--install|--update|--uninstall]'; exit 0 ;;
        *) fail "Unknown option: $arg" ;;
    esac
done

check_host() {
    [[ $EUID -ne 0 ]] || fail 'Run as your normal user, without sudo. The menu asks for sudo when needed.'
    [[ -d /run/systemd/system ]] || fail 'Raspberry Pi OS / Debian with systemd is required.'
    [[ "$project_dir" =~ ^/[a-zA-Z0-9_./-]+$ ]] || fail 'Use a project path without spaces or special characters.'
    [[ -O "$project_dir" && -w "$project_dir" ]] || fail 'The project directory must belong to your account and be writable.'
    command -v sudo >/dev/null || fail 'sudo is required.'
    command -v python3 >/dev/null || fail 'python3 is required.'
    sudo -v
    local installed_dir
    installed_dir="$(systemctl show "$service" -p WorkingDirectory --value 2>/dev/null || true)"
    [[ -z "$installed_dir" || "$installed_dir" == "$project_dir" ]] || fail "MeshcoreStation is installed at $installed_dir; use its setup menu."
}

require_installation() {
    [[ -f "$project_dir/meshcorestation.env" ]] || fail 'MeshcoreStation is not installed in this directory.'
    [[ -x "$project_dir/.venv/bin/python3" ]] || fail 'MeshcoreStation virtual environment is missing. Run Install / repair.'
}

choose_port() {
    local answer
    while true; do
        ask 'Web port [80]: ' answer
        answer="${answer:-80}"
        if [[ "$answer" =~ ^[0-9]{1,5}$ ]] && ((10#$answer >= 1 && 10#$answer <= 65535)); then
            web_port=$((10#$answer))
            return
        fi
        echo 'Enter a number from 1 to 65535.'
    done
}

check_port() {
    sudo python3 - "$web_port" <<'PY'
import socket, sys
with socket.socket() as listener:
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(('0.0.0.0', int(sys.argv[1])))
    except OSError as exc:
        raise SystemExit(f'Port {sys.argv[1]} is unavailable: {exc}. Choose another port or stop its current service.')
PY
}

apt_packages() {
    local opts=(-o Acquire::ForceIPv4=true -o Acquire::Retries=2 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30)
    sudo apt-get "${opts[@]}" update
    sudo apt-get "${opts[@]}" install -y python3 python3-venv python3-pip python3-dev build-essential libffi-dev libssl-dev pkg-config rustc cargo tzdata git
}

install_python_dependencies() {
    local py="$1" work_dir="$2"
    "$py" -m pip install -r "$project_dir/requirements.txt"
    PYTHONPATH="$project_dir" "$py" "$project_dir/scripts/check_dependencies.py"
    cd -- "$project_dir"
    PYTHONPATH="$project_dir" "$py" scripts/check_install.py
    "$py" -m pip freeze > requirements-installed.txt
}

write_service_unit() {
    local target="$1" service_user="$2" service_group="$3"
    cat > "$target" <<UNIT
[Unit]
Description=MeshcoreStation
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$service_user
Group=$service_group
SupplementaryGroups=dialout
WorkingDirectory=$project_dir
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$project_dir/meshcorestation.env
ExecStart=$project_dir/.venv/bin/python3 -m meshcorestation
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=on-failure
RestartSec=10
TimeoutStopSec=45
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
}

install_service_files() {
    local work_dir="$1" service_user="$2" service_group="$3"
    write_service_unit "$work_dir/$service" "$service_user" "$service_group"
    systemd-analyze verify "$work_dir/$service"
    sudo install -o root -g root -m 0644 "$work_dir/$service" "/etc/systemd/system/$service"
    sudo install -o root -g root -m 0755 scripts/meshcorestation /usr/local/bin/meshcorestation
    install_web_updater "$work_dir" "$service_user" "$service_group"
    sudo systemctl daemon-reload
    sudo systemctl enable meshcorestation-update.service
    sudo systemctl enable --now meshcorestation-update.path
}

install_web_updater() {
    local work_dir="$1" service_user="$2" service_group="$3"
    mkdir -p "$project_dir/.updates"
    chmod 0700 "$project_dir/.updates"
    cat > "$work_dir/meshcorestation-update.service" <<UNIT
[Unit]
Description=MeshcoreStation web update worker
After=network-online.target

[Service]
Type=oneshot
User=$service_user
Group=$service_group
WorkingDirectory=$project_dir
EnvironmentFile=$project_dir/meshcorestation.env
Environment=PYTHONPATH=$project_dir
ExecStart=/usr/bin/python3 -m meshcorestation.updater
TimeoutStartSec=infinity
Restart=on-failure
RestartSec=5
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
    cat > "$work_dir/meshcorestation-update.path" <<UNIT
[Unit]
Description=Watch for MeshcoreStation update requests

[Path]
PathExists=$project_dir/.updates/request.json
Unit=meshcorestation-update.service

[Install]
WantedBy=multi-user.target
UNIT
    # Only the two fixed service operations are permitted without a password.
    printf '%s ALL=(root) NOPASSWD: /usr/bin/systemctl stop meshcorestation.service, /usr/bin/systemctl start meshcorestation.service\n' "$service_user" > "$work_dir/meshcorestation-update-sudoers"
    sudo visudo -cf "$work_dir/meshcorestation-update-sudoers"
    sudo install -o root -g root -m 0440 "$work_dir/meshcorestation-update-sudoers" /etc/sudoers.d/meshcorestation-update
    for unit in meshcorestation-update.service meshcorestation-update.path; do
        systemd-analyze verify "$work_dir/$unit"
        sudo install -o root -g root -m 0644 "$work_dir/$unit" "/etc/systemd/system/$unit"
    done
}

install_project() (
    check_host
    choose_port
    local service_user service_group work_dir was_active=0 completed=0
    service_user="$(id -un)"; service_group="$(id -gn)"
    [[ "$service_user" =~ ^[a-z_][a-z0-9_-]*$ && "$service_group" =~ ^[a-z_][a-z0-9_-]*$ ]] || fail 'Unsupported user or group name.'
    python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ is required (Raspberry Pi OS Trixie is supported)."'
    for path in data .venv meshcorestation.env; do
        [[ ! -L "$project_dir/$path" ]] || fail "$path must not be a symlink."
    done
    if (( ! skip_apt )); then apt_packages; fi
    work_dir="$(mktemp -d)"
    trap 'result=$?; rm -rf -- "$work_dir"; if ((result)); then echo "Setup failed; correct the reported error and rerun this menu." >&2; if ((was_active && ! completed)); then sudo systemctl start "$service" || true; fi; fi' EXIT
    if systemctl is-active --quiet "$service"; then was_active=1; fi
    if systemctl cat "$service" >/dev/null 2>&1; then sudo systemctl stop "$service"; fi
    check_port
    echo 'Installing dependencies. Local native builds can take several minutes on a Pi Zero.'
    python3 -m venv "$project_dir/.venv"
    local py="$project_dir/.venv/bin/python3"
    install_python_dependencies "$py" "$work_dir"
    getent group dialout >/dev/null || fail 'The dialout group is required for serial access.'
    sudo usermod -aG dialout "$service_user"
    mkdir -p data
    chmod 0700 data
    if [[ -f meshcorestation.env ]]; then cp -p meshcorestation.env "meshcorestation.env.backup-$(date +%Y%m%d-%H%M%S)"; fi
    cat > "$work_dir/meshcorestation.env" <<ENV
MESHCORESTATION_DATA_DIR=$project_dir/data
MESHCORESTATION_HOST=0.0.0.0
MESHCORESTATION_PORT=$web_port
MESHCORESTATION_TIMEZONE=Europe/Berlin
ENV
    install -m 0600 "$work_dir/meshcorestation.env" meshcorestation.env
    install_service_files "$work_dir" "$service_user" "$service_group"
    sudo systemctl enable --now "$service"
    completed=1
    printf '\nMeshcoreStation installed; web port %s. Use the Pi hostname or IP in your browser.\n' "$web_port"
    echo 'In Settings, select the serial port and then select your bot channel.'
    echo 'Use meshcorestation status and meshcorestation recent to confirm startup and the radio connection.'
)

apply_update() (
    check_host
    require_installation
    # Native fallback builds need the same toolchain as a fresh installation.
    if (( ! skip_apt )); then apt_packages; fi
    local service_user service_group work_dir completed=0 restart_after
    service_user="$(id -un)"; service_group="$(id -gn)"
    restart_after="${MESHCORESTATION_UPDATE_RESTART:-1}"
    [[ "$restart_after" == 0 || "$restart_after" == 1 ]] || restart_after=1
    work_dir="$(mktemp -d)"
    trap 'result=$?; rm -rf -- "$work_dir"; if ((result && ! completed)); then echo "Update setup failed. The source checkout was updated, but the service may need repair." >&2; if ((restart_after)); then sudo systemctl start "$service" || true; fi; fi' EXIT
    sudo systemctl stop "$service" 2>/dev/null || true
    install_python_dependencies "$project_dir/.venv/bin/python3" "$work_dir"
    install_service_files "$work_dir" "$service_user" "$service_group"
    if ((restart_after)); then
        sudo systemctl enable --now "$service"
    else
        sudo systemctl enable "$service"
    fi
    completed=1
    local version
    version="$(PYTHONPATH="$project_dir" "$project_dir/.venv/bin/python3" -c 'from meshcorestation import __version__; print(__version__)')"
    printf '\nMeshcoreStation updated successfully to %s.\n' "$version"
)

update_project() (
    check_host
    require_installation
    command -v git >/dev/null || fail 'git is required for updates. Install git or run Install / repair once.'
    [[ -d "$project_dir/.git" ]] || fail 'Manual updates require MeshcoreStation to be installed from a Git clone.'
    cd -- "$project_dir"
    [[ -z "$(git status --porcelain --untracked-files=normal)" ]] || fail 'The Git working tree has local changes. Commit, stash, or remove them before updating.'
    local branch remote upstream local_commit remote_commit was_active=0
    branch="$(git symbolic-ref --quiet --short HEAD)" || fail 'Updates require a checked-out branch, not detached HEAD.'
    upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)" || fail "Branch $branch has no upstream tracking branch."
    remote="$(git config --get "branch.$branch.remote" || true)"
    [[ -n "$remote" ]] || fail "Cannot determine the Git remote for branch $branch."
    echo "Checking $upstream for updates..."
    git fetch --prune "$remote"
    local_commit="$(git rev-parse HEAD)"
    remote_commit="$(git rev-parse '@{u}')"
    if [[ "$local_commit" == "$remote_commit" ]]; then
        echo 'MeshcoreStation is already up to date.'
        exit 0
    fi
    git merge-base --is-ancestor "$local_commit" "$remote_commit" || fail 'The local and remote branches have diverged. Update aborted; only fast-forward updates are allowed.'
    mkdir -p "$project_dir/.updates"
    exec 9>"$project_dir/.updates/lock"
    flock -n 9 || fail 'A web update is already running.'
    if systemctl is-active --quiet "$service"; then was_active=1; fi
    ((was_active)) && sudo systemctl stop "$service"
    trap 'result=$?; if ((result && was_active)); then sudo systemctl start "$service" || true; fi' EXIT
    git merge --ff-only "$remote_commit"
    trap - EXIT
    export MESHCORESTATION_UPDATE_RESTART="$was_active"
    exec bash "$project_dir/install.sh" --apply-update
)

change_port() (
    check_host
    require_installation
    choose_port
    local was_active=0 changed=0
    systemctl is-active --quiet "$service" && was_active=1
    trap 'if ((was_active && ! changed)); then sudo systemctl start "$service" || true; fi' EXIT
    sudo systemctl stop "$service"
    check_port
    cp -p "$project_dir/meshcorestation.env" "$project_dir/meshcorestation.env.backup-$(date +%Y%m%d-%H%M%S)"
    python3 - "$project_dir/meshcorestation.env" "$web_port" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
lines = [line for line in path.read_text().splitlines() if not line.startswith('MESHCORESTATION_PORT=')]
path.write_text('\n'.join(lines + ['MESHCORESTATION_PORT=' + sys.argv[2]]) + '\n')
PY
    if ((was_active)); then sudo systemctl start "$service"; fi
    changed=1
    echo "Web port changed to $web_port."
)

uninstall_project() (
    check_host
    local answer
    echo 'This removes the MeshcoreStation service, command and virtual environment. Source files stay here.'
    ask 'Uninstall MeshcoreStation? [y/N]: ' answer
    [[ "$answer" == y || "$answer" == Y ]] || return 0
    if systemctl cat "$service" >/dev/null 2>&1; then sudo systemctl disable --now "$service"; fi
    sudo systemctl disable --now meshcorestation-update.path || true
    sudo systemctl disable --now meshcorestation-update.service || true
    sudo rm -f -- /etc/systemd/system/meshcorestation-update.path /etc/systemd/system/meshcorestation-update.service /etc/sudoers.d/meshcorestation-update
    sudo rm -f -- "/etc/systemd/system/$service" /usr/local/bin/meshcorestation
    sudo systemctl daemon-reload
    sudo systemctl reset-failed "$service" 2>/dev/null || true
    rm -rf -- "$project_dir/.venv"
    echo 'Database, settings, histories and logs are preserved by default.'
    ask 'Type DELETE to also erase MeshcoreStation data and configuration, or press Enter to keep them: ' answer
    if [[ "$answer" == DELETE ]]; then
        rm -rf -- "$project_dir/data"
        rm -f -- "$project_dir/meshcorestation.env" "$project_dir"/meshcorestation.env.backup-*
        echo 'MeshcoreStation data and configuration removed.'
    fi
    echo 'MeshcoreStation uninstalled. System packages and other applications were not removed.'
)

if [[ "$mode" == install ]]; then install_project; exit; fi
if [[ "$mode" == update ]]; then update_project; exit; fi
if [[ "$mode" == apply_update ]]; then apply_update; exit; fi
if [[ "$mode" == uninstall ]]; then uninstall_project; exit; fi
while true; do
    printf '\n  MeshcoreStation Setup\n  =====================\n  1) Install / repair\n  2) Update from GitHub\n  3) Change web port\n  4) Start\n  5) Stop\n  6) Restart\n  7) Status\n  8) Recent logs\n  9) Uninstall\n  0) Exit\n\n'
    ask 'Select an option: ' choice
    case "$choice" in
        1) install_project ;;
        2) update_project ;;
        3) change_port ;;
        4) sudo systemctl start "$service" ;;
        5) sudo systemctl stop "$service" ;;
        6) sudo systemctl restart "$service" ;;
        7) systemctl status "$service" --no-pager || true ;;
        8) journalctl -u "$service" -n 80 --no-pager ;;
        9) uninstall_project ;;
        0) exit 0 ;;
        *) echo 'Choose a listed option.' ;;
    esac
done
