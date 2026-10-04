#!/usr/bin/env bash
set -euo pipefail
umask 077
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bash "$repo_root/scripts/check-destroy-config.sh"
[[ ${DEPLOY_ACTION:-plan} == plan || ${DEPLOY_ACTION:-plan} == apply ]]
[[ ${LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT:-} =~ ^[a-z0-9]{3,24}$ ]] || {
  echo 'Complete the persistent archive setup in docs/livedocs-deployment.md first.' >&2; exit 1;
}
cd "$repo_root/environments/development"
export TF_IN_AUTOMATION=true TF_INPUT=false TF_WORKSPACE=default TF_LOG=OFF
export ARM_USE_OIDC=true ARM_USE_AZUREAD=true TF_VAR_enable_livedocs=true
unset TF_LOG_PATH TF_CLI_ARGS TF_CLI_ARGS_init TF_CLI_ARGS_plan TF_CLI_ARGS_apply
work_dir=$(mktemp -d)
phase=release-validation
cleanup() {
  code=$?
  rm -rf -- "$work_dir"
  if (( code != 0 )); then
    printf '::error::LiveDocs deployment failed during %s. Raw diagnostics are withheld; inspect securely. Recorded resources remain available to the destroy workflow.\n' "$phase" >&2
  fi
}
trap cleanup EXIT
python3 "$repo_root/scripts/check-livedocs-release.py" "$repo_root/releases/livedocs.json" --verify-publication
phase=archive-verification
az storage account show --name "$LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT" \
  --resource-group rg-ecommerce-livedocs-archive --subscription "$ARM_SUBSCRIPTION_ID" \
  --output none >"$work_dir/archive.log" 2>&1
phase=initialization
terraform init -input=false -reconfigure -lockfile=readonly \
  "-backend-config=resource_group_name=$TFSTATE_RESOURCE_GROUP" \
  "-backend-config=storage_account_name=$TFSTATE_STORAGE_ACCOUNT" \
  "-backend-config=container_name=$TFSTATE_CONTAINER" \
  '-backend-config=key=ecommerce/development.tfstate' >"$work_dir/init.log" 2>&1
phase=validation
terraform validate -no-color >"$work_dir/validate.log" 2>&1
phase=planning
terraform plan -input=false -lock=true -lock-timeout=5m \
  -out="$work_dir/livedocs.tfplan" >"$work_dir/plan.log" 2>&1
terraform show -json "$work_dir/livedocs.tfplan" >"$work_dir/plan.json" 2>"$work_dir/show.log"
phase=plan-policy
python3 "$repo_root/scripts/validate-livedocs-plan.py" "$work_dir/plan.json" | tee "$work_dir/review.txt"
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then cat "$work_dir/review.txt" >>"$GITHUB_STEP_SUMMARY"; fi
if [[ ${DEPLOY_ACTION:-plan} == plan ]]; then
  echo 'Plan only: no resources applied. The private plan is discarded; apply runs create and review a fresh plan.'
  exit 0
fi
phase=application
terraform apply -input=false -lock=true -lock-timeout=5m \
  "$work_dir/livedocs.tfplan" >"$work_dir/apply.log" 2>&1
phase=public-verification
terraform output -json livedocs >"$work_dir/output.json" 2>"$work_dir/output.log"
portal=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["portal_url"])' "$work_dir/output.json")
commit=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit_sha"])' "$work_dir/output.json")
python3 "$repo_root/scripts/smoke-livedocs.py" "$portal" "$commit"
phase=archive-verification
az storage account show --name "$LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT" \
  --resource-group rg-ecommerce-livedocs-archive --subscription "$ARM_SUBSCRIPTION_ID" \
  --output none >"$work_dir/archive-after.log" 2>&1
printf 'LiveDocs deployed and verified: %s\n' "$portal"
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  printf '\nLiveDocs: %s\n\nHTTPS routes/source identity verified; persistent archive account retained.\n' "$portal" >>"$GITHUB_STEP_SUMMARY"
fi
