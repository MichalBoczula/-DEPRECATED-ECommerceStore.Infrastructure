#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
[[ ${GITHUB_REPOSITORY:-} == MichalBoczula/ECommerceStore.Infrastructure ]]
[[ ${GITHUB_EVENT_NAME:-} == workflow_run ]]
version=$(tr -d '\r\n' <modules/VERSION)
[[ $version =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]
tag="modules-v$version"
commit=${MODULE_RELEASE_COMMIT:?Missing tested main commit.}
[[ $commit =~ ^[a-f0-9]{40}$ && $(git rev-parse HEAD) == "$commit" ]]

if git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
  if ! git diff --quiet "$tag" "$commit" -- modules; then
    echo 'Module content changed without a version bump. Existing tags are never moved.' >&2
    exit 1
  fi
  printf 'Existing %s retained; module content is unchanged.\n' "$tag"
else
  gh api --method POST "repos/$GITHUB_REPOSITORY/git/refs" \
    -f "ref=refs/tags/$tag" -f "sha=$commit" >/dev/null
  printf 'Published %s at the successfully tested main commit.\n' "$tag"
fi
