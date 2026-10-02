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
    printf '::error::Development teardown failed during %s. Raw Terraform logs are withheld because they can contain secrets. Investigate securely; do not force-unlock an active run.\n' "$phase" >&2
  fi
}
trap cleanup EXIT

# No credentials in backend-config, no state migration, no local fallback.
terraform init -input=false -reconfigure -lockfile=readonly \
  "-backend-config=resource_group_name=$TFSTATE_RESOURCE_GROUP" \
  "-backend-config=storage_account_name=$TFSTATE_STORAGE_ACCOUNT" \
  "-backend-config=container_name=$TFSTATE_CONTAINER" \
  '-backend-config=key=ecommerce/development.tfstate' >"$work_dir/init.log" 2>&1

phase=validation
terraform validate -no-color >"$work_dir/validate.log" 2>&1
phase=planning
terraform plan -destroy -input=false -lock=true -lock-timeout=5m \
  -out="$work_dir/destroy.tfplan" >"$work_dir/plan.log" 2>&1
terraform show -json "$work_dir/destroy.tfplan" >"$work_dir/plan.json" 2>"$work_dir/show.log"
phase=plan-policy
delete_count=$(python3 "$repo_root/scripts/validate-destroy-plan.py" "$work_dir/plan.json")

phase=application
# Apply this exact complete destroy plan. Never use -target or -lock=false.
terraform apply -input=false -lock=true -lock-timeout=5m \
  "$work_dir/destroy.tfplan" >"$work_dir/apply.log" 2>&1

phase=state-verification
terraform state list >"$work_dir/resources.txt" 2>"$work_dir/state.log"
[[ ! -s "$work_dir/resources.txt" ]]
phase=resource-group-verification
az group exists --name rg-ecommerce-dev --subscription "$ARM_SUBSCRIPTION_ID" \
  --output tsv >"$work_dir/group.txt" 2>"$work_dir/group.log"
[[ $(tr -d '\r\n' <"$work_dir/group.txt") == false ]]
phase=backend-verification
az storage account show --name "$TFSTATE_STORAGE_ACCOUNT" \
  --resource-group "$TFSTATE_RESOURCE_GROUP" --output none \
  >"$work_dir/backend.log" 2>&1

printf 'Development destroy completed: %s planned deletions; state empty; application resource group absent; state storage account retained.\n' "$delete_count"
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  {
    printf '### Development teardown\n\n'
    printf -- '- Planned deletions: %s\n' "$delete_count"
    printf -- '- Terraform state: empty\n- rg-ecommerce-dev: absent\n- Independent state storage account: retained\n'
    printf '\nD/18 must also verify ACA managed groups, soft-deleted resources, retained backups and remaining billing.\n'
  } >>"$GITHUB_STEP_SUMMARY"
fi
