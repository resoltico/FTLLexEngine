#!/usr/bin/env bash
# Ensure devcontainer-managed cache mounts stay writable for the remote user.

set -euo pipefail

current_user="$(id -un)"
current_group="$(id -gn)"
home_dir="${HOME:-/home/${current_user}}"

repair_path() {
    local target_path="$1"

    sudo install -d -o "${current_user}" -g "${current_group}" "${target_path}"

    if find "${target_path}" ! -user "${current_user}" -print -quit | grep -q .; then
        sudo chown -R "${current_user}:${current_group}" "${target_path}"
    fi
}

repair_path "${home_dir}/.cache"
