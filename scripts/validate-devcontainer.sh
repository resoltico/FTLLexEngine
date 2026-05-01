#!/usr/bin/env bash
# Build-time and contract-level validation for the committed contributor devcontainer surface.

set -euo pipefail

die() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

resolve_script_dir() {
    local source_path="${BASH_SOURCE[0]}"
    while [[ -h "${source_path}" ]]; do
        local source_dir
        source_dir="$(cd -P -- "$(dirname -- "${source_path}")" && pwd)"
        source_path="$(readlink "${source_path}")"
        if [[ "${source_path}" != /* ]]; then
            source_path="${source_dir}/${source_path}"
        fi
    done
    cd -P -- "$(dirname -- "${source_path}")" && pwd
}

repo_root="$(cd "$(resolve_script_dir)/.." && pwd)"
readonly repo_root
readonly dockerfile_path="${repo_root}/.devcontainer/Dockerfile"
readonly config_path="${repo_root}/.devcontainer/devcontainer.json"
readonly user_home_repair_script="${repo_root}/scripts/devcontainer-prepare-user-home.sh"

command -v docker >/dev/null 2>&1 || die "docker is required to validate the contributor devcontainer"
command -v python3 >/dev/null 2>&1 || die "python3 is required to validate devcontainer.json"
[[ -f "${dockerfile_path}" ]] || die "missing ${dockerfile_path}"
[[ -f "${config_path}" ]] || die "missing ${config_path}"
[[ -f "${user_home_repair_script}" ]] || die "missing ${user_home_repair_script}"

python3 - <<'PY' "${config_path}"
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text())

expected_feature = "ghcr.io/devcontainers/features/docker-outside-of-docker:1"
features = config.get("features", {})
if expected_feature not in features:
    raise SystemExit(f"missing {expected_feature} feature")

build = config.get("build", {})
if build.get("dockerfile") != "Dockerfile":
    raise SystemExit("devcontainer build.dockerfile must stay 'Dockerfile'")
if build.get("context") != ".":
    raise SystemExit("devcontainer build.context must stay '.'")

if config.get("remoteUser") != "vscode":
    raise SystemExit("remoteUser must stay 'vscode'")

if config.get("workspaceFolder") != "/workspaces/ftllexengine":
    raise SystemExit("workspaceFolder must stay /workspaces/ftllexengine")

workspace_mount = config.get("workspaceMount", "")
if "target=/workspaces/ftllexengine" not in workspace_mount:
    raise SystemExit("workspaceMount must bind into /workspaces/ftllexengine")
if "consistency=cached" in workspace_mount:
    raise SystemExit("workspaceMount must not use consistency=cached")

mounts = config.get("mounts", [])
if not any("target=/home/vscode/.cache" in mount for mount in mounts):
    raise SystemExit("devcontainer must keep a named general cache volume")

env = config.get("containerEnv", {})
if env.get("FTLLEXENGINE_DEVCONTAINER") != "1":
    raise SystemExit("devcontainer must set FTLLEXENGINE_DEVCONTAINER=1")
if env.get("CLANG_BIN") != "/usr/local/bin/clang":
    raise SystemExit("devcontainer must expose CLANG_BIN=/usr/local/bin/clang")
if env.get("UV_LINK_MODE") != "copy":
    raise SystemExit("devcontainer must set UV_LINK_MODE=copy for bind-mounted workspace installs")

if config.get("postStartCommand") != "./scripts/devcontainer-prepare-user-home.sh":
    raise SystemExit("devcontainer must repair cache mounts on start")

settings = config.get("customizations", {}).get("vscode", {}).get("settings", {})
if settings.get("terminal.integrated.defaultProfile.linux") != "bash":
    raise SystemExit("devcontainer must default terminals to bash")

extensions = config.get("customizations", {}).get("vscode", {}).get("extensions", [])
for extension_id in (
    "ms-python.python",
    "ms-python.mypy-type-checker",
    "charliermarsh.ruff",
):
    if extension_id not in extensions:
        raise SystemExit(f"{extension_id} must remain installed in the devcontainer")
PY

readonly image_tag="ftllexengine-devcontainer-validate:local"
readonly cache_volume="ftllexengine-devcontainer-validate-cache-$$"

cleanup() {
    docker volume rm -f "${cache_volume}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker build \
    --file "${dockerfile_path}" \
    --tag "${image_tag}" \
    "${repo_root}/.devcontainer" >/dev/null

docker run --rm "${image_tag}" bash -lc '
    set -euo pipefail
    python3.13 --version | grep -E "^Python 3\.13" >/dev/null
    uv --version >/dev/null
    git --version >/dev/null
    bash --version | head -1 | grep -E "version 5" >/dev/null
    shellcheck --version >/dev/null
    clang --version >/dev/null
    test -n "$(find "$(clang --print-resource-dir)"/lib/linux -maxdepth 1 -name "libclang_rt.fuzzer*.a" -print -quit)"
'

docker run --rm \
    --env CLANG_BIN=/usr/local/bin/clang \
    --env UV_LINK_MODE=copy \
    "${image_tag}" bash -lc '
    set -euo pipefail
    test "${CLANG_BIN}" = "/usr/local/bin/clang"
    test "${UV_LINK_MODE}" = "copy"
'

docker volume create "${cache_volume}" >/dev/null

docker run --rm --user root \
    --volume "${cache_volume}:/home/vscode/.cache" \
    "${image_tag}" bash -lc '
        set -euo pipefail
        install -d -o root -g root /home/vscode/.cache/uv
        touch /home/vscode/.cache/uv/root-owned-marker
    '

docker run --rm \
    --interactive \
    --volume "${cache_volume}:/home/vscode/.cache" \
    "${image_tag}" bash -lc '
        set -euo pipefail
        cat > /tmp/devcontainer-prepare-user-home.sh
        chmod +x /tmp/devcontainer-prepare-user-home.sh
        /tmp/devcontainer-prepare-user-home.sh
        touch /home/vscode/.cache/uv/user-writable-marker
    ' < "${user_home_repair_script}"

printf 'devcontainer validation: success\n'
