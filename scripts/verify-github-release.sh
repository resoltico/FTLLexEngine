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

readonly script_dir="$(resolve_script_dir)"
readonly repo_root="$(cd -P -- "${script_dir}/.." && pwd)"
readonly normalized_name="$(read_pyproject_field normalized_name)"
readonly version="$(read_pyproject_field version)"
readonly tag_name="${1:-${RELEASE_TAG:-${GITHUB_REF_NAME:-}}}"
readonly expected_tag="v${version}"
readonly expected_assets=(
    "${normalized_name}-${version}.tar.gz"
    "${normalized_name}-${version}-py3-none-any.whl"
    "${normalized_name}-${version}.sha256"
)

[[ -n "${GH_TOKEN:-}" ]] || die "GH_TOKEN is required"
[[ -n "${tag_name}" ]] || die "tag name is required"
[[ "${tag_name}" == "${expected_tag}" ]] || die "expected tag ${expected_tag}, got ${tag_name}"

release_tag="$(gh release view "${tag_name}" --json tagName --jq '.tagName')"
[[ "${release_tag}" == "${tag_name}" ]] || die \
    "expected release tag ${tag_name}, got ${release_tag}"

is_draft="$(gh release view "${tag_name}" --json isDraft --jq '.isDraft')"
[[ "${is_draft}" == "false" ]] || die "release ${tag_name} is still a draft"

is_prerelease="$(gh release view "${tag_name}" --json isPrerelease --jq '.isPrerelease')"
[[ "${is_prerelease}" == "false" ]] || die "release ${tag_name} is marked prerelease"

for asset_name in "${expected_assets[@]}"; do
    has_asset="$(gh release view "${tag_name}" --json assets --jq \
        ".assets | map(.name) | index(\"${asset_name}\") != null")"
    [[ "${has_asset}" == "true" ]] || die \
        "release ${tag_name} is missing required asset ${asset_name}"
done

release_url="$(gh release view "${tag_name}" --json url --jq '.url')"
printf 'Verified GitHub release handoff: %s\n' "${release_url}"
