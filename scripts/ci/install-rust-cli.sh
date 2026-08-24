#!/usr/bin/env bash
set -euo pipefail

bin_dir=""
release_tag="${RUST_CLI_RELEASE_TAG:-}"
while (($#)); do
  case "$1" in
    --bin-dir) bin_dir="${2:?--bin-dir requires a value}"; shift 2 ;;
    --release-tag) release_tag="${2:?--release-tag requires a value}"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$bin_dir" ]] || { echo '--bin-dir is required' >&2; exit 2; }
command -v gh >/dev/null || { echo 'gh CLI is required' >&2; exit 2; }
command -v sha256sum >/dev/null || { echo 'sha256sum is required' >&2; exit 2; }

if [[ -z "$release_tag" ]]; then
  release_tag="$(gh release list --repo "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}" --limit 100 --json tagName,publishedAt,isDraft,isPrerelease |
    jq -er '[.[] | select((.tagName | startswith("rust-v")) and (.isDraft == false) and (.isPrerelease == false))] | sort_by(.publishedAt) | last | .tagName')" || {
      echo 'no published rust-v* workspace CLI release is available' >&2
      exit 1
    }
fi
[[ "$release_tag" == rust-v* ]] || { echo 'Rust CLI release tag must start with rust-v' >&2; exit 2; }

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
gh release download "$release_tag" --repo "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}" \
  --pattern 'rust-workspace-*.tar.gz' --pattern 'rust-workspace-*.sha256' --dir "$tmp_dir"
mapfile -t archives < <(find "$tmp_dir" -maxdepth 1 -type f -name 'rust-workspace-*.tar.gz')
mapfile -t checksums < <(find "$tmp_dir" -maxdepth 1 -type f -name 'rust-workspace-*.sha256')
[[ ${#archives[@]} -eq 1 && ${#checksums[@]} -eq 1 ]] || { echo 'workspace release must contain exactly one archive and checksum' >&2; exit 1; }
(cd "$tmp_dir" && sha256sum -c "$(basename "${checksums[0]}")")
rm -rf "$bin_dir"
mkdir -p "$bin_dir"
tar -xzf "${archives[0]}" -C "$bin_dir"
for binary in asr-rtf-rank asr-rtf-cost-policy asr-rtf-service; do
  [[ -x "$bin_dir/bin/$binary" ]] || { echo "release is missing executable $binary" >&2; exit 1; }
done
mv "$bin_dir/bin"/* "$bin_dir/"
rmdir "$bin_dir/bin"
echo "Installed Rust workspace CLI release $release_tag into $bin_dir"
