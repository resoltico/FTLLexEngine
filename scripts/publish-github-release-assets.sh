#!/usr/bin/env bash

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

read_pyproject_field() {
    local field="$1"
    python3 - "${repo_root}/pyproject.toml" "${field}" <<'PY'
from __future__ import annotations

import sys
import tomllib

pyproject_path = sys.argv[1]
field = sys.argv[2]

with open(pyproject_path, "rb") as handle:
    project = tomllib.load(handle)["project"]

if field == "normalized_name":
    print(project["name"].replace("-", "_"))
elif field == "version":
    print(project["version"])
else:
    raise SystemExit(f"unsupported field: {field}")
PY
}

release_exists() {
    gh release view "${tag_name}" >/dev/null 2>&1
}

ensure_release() {
    if release_exists; then
        return
    fi

    if gh release create "${tag_name}" --verify-tag --title "${tag_name}" --generate-notes \
        >/dev/null 2>&1; then
        return
    fi

    release_exists || die "failed to converge GitHub release ${tag_name}"
}

release_has_asset() {
    local asset_name="$1"
    gh release view "${tag_name}" --json assets --jq \
        ".assets | map(.name) | index(\"${asset_name}\") != null"
}

upload_if_missing() {
    local asset_path="$1"
    local asset_name
    asset_name="$(basename -- "${asset_path}")"

    [[ -f "${asset_path}" ]] || die "missing asset ${asset_path}"

    if [[ "$(release_has_asset "${asset_name}")" == "true" ]]; then
        return
    fi

    if gh release upload "${tag_name}" "${asset_path}" >/dev/null 2>&1; then
        return
    fi

    [[ "$(release_has_asset "${asset_name}")" == "true" ]] || die \
        "failed to upload ${asset_name} to release ${tag_name}"
}

readonly script_dir="$(resolve_script_dir)"
readonly repo_root="$(cd -P -- "${script_dir}/.." && pwd)"
readonly normalized_name="$(read_pyproject_field normalized_name)"
readonly version="$(read_pyproject_field version)"
readonly tag_name="${1:-${RELEASE_TAG:-${GITHUB_REF_NAME:-}}}"
readonly expected_tag="v${version}"

[[ -n "${GH_TOKEN:-}" ]] || die "GH_TOKEN is required"
[[ -n "${tag_name}" ]] || die "tag name is required"
[[ "${tag_name}" == "${expected_tag}" ]] || die "expected tag ${expected_tag}, got ${tag_name}"

readonly assets=(
    "${repo_root}/dist/${normalized_name}-${version}.tar.gz"
    "${repo_root}/dist/${normalized_name}-${version}-py3-none-any.whl"
    "${repo_root}/dist/${normalized_name}-${version}.sha256"
)

ensure_release

for asset_path in "${assets[@]}"; do
    upload_if_missing "${asset_path}"
done

printf 'GitHub release asset upload converged for %s\n' "${tag_name}"
