#!/usr/bin/env bash
set -euo pipefail
umask 077
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bash "$repo_root/scripts/check-destroy-config.sh"
cd "$repo_root/environments/development"
export TF_IN_AUTOMATION=true TF_INPUT=false TF_WORKSPACE=default
export ARM_USE_OIDC=true ARM_USE_AZUREAD=true TF_LOG=OFF
unset TF_LOG_PATH TF_CLI_ARGS TF_CLI_ARGS_init TF_CLI_ARGS_plan TF_CLI_ARGS_apply
work_dir=$(mktemp -d)
phase=initialization
cleanup() {
  code=$?
  rm -rf -- "$work_dir"
  if (( code != 0 )); then
    printf '::error::Backend verification failed during %s. Detailed Terraform logs are withheld.\n' "$phase" >&2
  fi
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
terraform plan -input=false -lock=true -lock-timeout=5m \
  -out="$work_dir/verify.tfplan" >"$work_dir/plan.log" 2>&1
terraform show -json "$work_dir/verify.tfplan" >"$work_dir/plan.json" 2>"$work_dir/show.log"
phase=no-change-policy
python3 - "$work_dir/plan.json" <<'PY'
import json, sys
with open(sys.argv[1]) as f: plan = json.load(f)
if any(r.get('mode') == 'managed' and r['change']['actions'] != ['no-op'] for r in plan.get('resource_changes', [])):
    sys.exit('Verification stopped: use the deployment workflow to review and apply resource changes.')
PY
phase=no-change-apply
# Persist the initial empty remote state, or an unchanged state. The policy
# above prohibits this verification workflow from changing managed resources.
terraform apply -input=false -lock=true -lock-timeout=5m \
  "$work_dir/verify.tfplan" >"$work_dir/apply.log" 2>&1
phase=remote-state-read
terraform state pull >"$work_dir/state.json" 2>"$work_dir/state.log"
python3 - "$work_dir/state.json" <<'PY'
import json, sys
with open(sys.argv[1]) as f: state = json.load(f)
assert state.get('lineage'), 'Remote state lineage is missing.'
PY
phase=azure-read-access
az group exists --name rg-ecommerce-dev --subscription "$ARM_SUBSCRIPTION_ID" \
  --output tsv >"$work_dir/group.txt" 2>"$work_dir/group.log"
[[ $(tr -d '\r\n' <"$work_dir/group.txt") == true ]]
az storage account show --name "$TFSTATE_STORAGE_ACCOUNT" \
  --resource-group "$TFSTATE_RESOURCE_GROUP" --output none >"$work_dir/backend.log" 2>&1
printf 'OIDC init, locked plan, no-change apply and remote state read succeeded. Development group and backend are readable.\n'
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  printf '### Development backend verified\n\nOIDC authentication, remote init, locked plan, no-change apply and state read passed. No managed application resources were changed.\n\nReal resource apply/destroy/reapply evidence remains in D/18.\n' >>"$GITHUB_STEP_SUMMARY"
fi
