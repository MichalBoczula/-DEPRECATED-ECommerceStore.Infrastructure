#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
account=$(terraform -chdir="$repo_root/foundations/livedocs" output -raw archive_storage_account | tr -d '\r\n')
[[ $account =~ ^[a-z0-9]{3,24}$ ]]
gh variable set LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT --env development \
  --repo MichalBoczula/ECommerceStore.Infrastructure --body "$account"
gh variable set LIVEDOCS_ENABLED --env development \
  --repo MichalBoczula/ECommerceStore.Infrastructure --body true
echo 'Development archive and host configuration saved. Existing D/2 ID secrets are unchanged.'
