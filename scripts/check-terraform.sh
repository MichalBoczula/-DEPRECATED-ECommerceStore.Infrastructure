#!/usr/bin/env bash
set -euo pipefail
umask 077
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
export TF_IN_AUTOMATION=true TF_INPUT=false TF_WORKSPACE=default TF_LOG=OFF
unset TF_LOG_PATH TF_CLI_ARGS TF_CLI_ARGS_init TF_CLI_ARGS_test
work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT

terraform fmt -check -recursive
for root in modules/deployment-context environments/development; do
  label=${root//\//-}
  terraform -chdir="$root" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="$root" validate -no-color
  status=0
  terraform -chdir="$root" test -test-directory=tests -verbose -json \
    >"$work_dir/$label.jsonl" 2>"$work_dir/$label.log" || status=$?
  if ! python3 scripts/render-test-plans.py "$work_dir/$label.jsonl" "$root" \
    >"$work_dir/$label.md"; then
    echo '::error::Offline Terraform tests failed; raw plan values and diagnostics are withheld.' >&2
    exit 1
  fi
  cat "$work_dir/$label.md"
  if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
    cat "$work_dir/$label.md" >>"$GITHUB_STEP_SUMMARY"
  fi
  (( status == 0 )) || { echo '::error::Terraform test failed.' >&2; exit "$status"; }
done

terraform -chdir=environments/development providers schema -json \
  >"$work_dir/providers.json"
python3 scripts/check-provider-schema.py "$work_dir/providers.json"
