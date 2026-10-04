#!/usr/bin/env bash
set -euo pipefail
umask 077
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root/foundations/livedocs"
[[ $# == 3 ]] || { echo 'Usage: bash scripts/init-livedocs-archive.sh STATE_RESOURCE_GROUP STATE_ACCOUNT INFRASTRUCTURE_PRINCIPAL_ID' >&2; exit 1; }
[[ $1 =~ ^[a-zA-Z0-9_.()-]{1,90}$ && ${1,,} != rg-ecommerce-livedocs-archive && ${1,,} != rg-ecommerce-dev ]]
[[ $2 =~ ^[a-z0-9]{3,24}$ ]]
[[ $3 =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]]
# Never silently reconfigure an existing local checkout to a different state.
[[ ! -e backend.hcl && ! -e setup.auto.tfvars.json && ! -d .terraform ]] || {
  echo 'Archive root already configured. Reuse its backend.hcl; investigate before replacing backend settings.' >&2; exit 1;
}
command -v terraform >/dev/null || { echo 'Terraform must be on this Bash terminal PATH.' >&2; exit 1; }
command -v az >/dev/null || { echo 'Azure CLI must be on this Bash terminal PATH.' >&2; exit 1; }
subscription=$(az account show --query id --output tsv | tr -d '\r\n')
[[ $subscription =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]]
for provider in Microsoft.App Microsoft.Network Microsoft.Storage; do
  status=$(az provider show --namespace "$provider" --query registrationState --output tsv | tr -d '\r\n')
  [[ $status == Registered ]] || { printf 'Operator must register %s before setup.\n' "$provider" >&2; exit 1; }
done
# The independent state container is the explicit exception to Terraform ownership.
# No state account creation, credentials, account key or SAS.
az storage account show --resource-group "$1" --name "$2" --output none
az storage container create --account-name "$2" --name livedocs-archive-state \
  --auth-mode login --public-access off --output none
cat >backend.hcl <<EOF
resource_group_name  = "$1"
storage_account_name = "$2"
container_name       = "livedocs-archive-state"
key                  = "ecommerce/livedocs-archive.tfstate"
EOF
printf '{"subscription_id":"%s","infrastructure_principal_id":"%s"}\n' "$subscription" "$3" >setup.auto.tfvars.json
terraform init -input=false -lockfile=readonly '-backend-config=backend.hcl'
echo 'Archive backend initialized. Review terraform plan, then apply the saved plan as documented.'
