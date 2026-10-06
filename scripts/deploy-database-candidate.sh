#!/usr/bin/env bash
set -euo pipefail
umask 077
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bash "$repo_root/scripts/check-destroy-config.sh"
[[ ${TF_VAR_enable_database_candidate:-false} == true ]]
[[ ${DEPLOY_ACTION:-} == plan || ${DEPLOY_ACTION:-} == apply ]]
cd "$repo_root/environments/development"
export TF_IN_AUTOMATION=true TF_INPUT=false TF_WORKSPACE=default
export ARM_USE_OIDC=true ARM_USE_AZUREAD=true TF_LOG=OFF
unset TF_LOG_PATH TF_CLI_ARGS TF_CLI_ARGS_init TF_CLI_ARGS_plan TF_CLI_ARGS_apply
work_dir=$(mktemp -d)
phase=initialization
cleanup() {
  code=$?
  if (( code != 0 )); then
    if [[ $phase == planning ]]; then
      python3 "$repo_root/scripts/report-test-failure.py" "$work_dir/plan.log" --deployment || true
      echo '::error::D/6 plan failed; no apply was attempted by this run. Raw diagnostics remain private.' >&2
    else
      printf '::error::D/6 candidate failed during %s; private Terraform details withheld.\n' "$phase" >&2
    fi
  fi
  rm -rf -- "$work_dir"
}
trap cleanup EXIT
terraform init -input=false -reconfigure -lockfile=readonly \
  "-backend-config=resource_group_name=$TFSTATE_RESOURCE_GROUP" \
  "-backend-config=storage_account_name=$TFSTATE_STORAGE_ACCOUNT" \
  "-backend-config=container_name=$TFSTATE_CONTAINER" \
  '-backend-config=key=ecommerce/development.tfstate' >"$work_dir/init.log" 2>&1
phase=validation
terraform validate -no-color >"$work_dir/validate.log" 2>&1
phase=planning
terraform plan -json -input=false -lock=true -lock-timeout=5m -out="$work_dir/candidate.tfplan" >"$work_dir/plan.log" 2>"$work_dir/plan-stderr.log"
terraform show -json "$work_dir/candidate.tfplan" >"$work_dir/plan.json" 2>"$work_dir/show.log"
phase=policy
python3 "$repo_root/scripts/validate-database-candidate.py" "$work_dir/plan.json"
if [[ $DEPLOY_ACTION == apply ]]; then
  phase=application
  terraform apply -input=false -lock=true -lock-timeout=5m "$work_dir/candidate.tfplan" >"$work_dir/apply.log" 2>&1
  phase=readback
  terraform output -json database_candidate >"$work_dir/names.json" 2>"$work_dir/output.log"
  python3 "$repo_root/scripts/validate-database-candidate.py" "$work_dir/names.json" --readback "$ARM_SUBSCRIPTION_ID"
  echo 'D/6 candidate provisioned and Free settings verified. Next: D/7 access from Container Apps, then D/9 application compatibility. Lifecycle proof is D/19.'
fi
