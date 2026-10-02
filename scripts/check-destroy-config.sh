#!/usr/bin/env bash
set -euo pipefail

fail() { printf '::error::%s\n' "$1" >&2; exit 1; }

[[ ${GITHUB_REPOSITORY:-} == MichalBoczula/ECommerceStore.Infrastructure ]] || fail 'This workflow targets the development repository only.'
[[ ${GITHUB_REF:-} == refs/heads/main ]] || fail 'Run this workflow from main.'

for name in ARM_CLIENT_ID ARM_TENANT_ID ARM_SUBSCRIPTION_ID TFSTATE_RESOURCE_GROUP TFSTATE_STORAGE_ACCOUNT TFSTATE_CONTAINER; do
  [[ -n ${!name:-} ]] || fail "Missing development configuration: $name. Complete D/2 first."
done

for name in ARM_CLIENT_ID ARM_TENANT_ID ARM_SUBSCRIPTION_ID; do
  [[ ${!name} =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]] || fail "Invalid UUID: $name."
done
[[ $TFSTATE_STORAGE_ACCOUNT =~ ^[a-z0-9]{3,24}$ ]] || fail 'Invalid state storage account name.'
[[ $TFSTATE_CONTAINER =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ && $TFSTATE_CONTAINER != *--* ]] || fail 'Invalid state container name.'
[[ $TFSTATE_RESOURCE_GROUP =~ ^[a-zA-Z0-9_.()-]{1,90}$ && $TFSTATE_RESOURCE_GROUP != *. ]] || fail 'Invalid bootstrap resource group name.'
[[ ${TFSTATE_RESOURCE_GROUP,,} != rg-ecommerce-dev ]] || fail 'The state store must be outside rg-ecommerce-dev.'
[[ ${TF_WORKSPACE:-default} == default ]] || fail 'Development uses the default workspace and its fixed dev state key.'
