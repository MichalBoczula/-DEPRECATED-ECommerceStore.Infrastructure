"""Read ACA-reported outbound IPs; never substitute a workstation or ingress IP."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import shutil
import subprocess


def public_ipv4(values):
    if not isinstance(values, list) or not 0 < len(values) <= 64:
        raise ValueError('A nonempty bounded IPv4 list is required')
    addresses = set()
    for value in values:
        address = ipaddress.IPv4Address(value)
        if str(address) != value or not address.is_global or address.is_multicast:
            raise ValueError('Only canonical public IPv4 addresses are accepted')
        addresses.add(value)
    return sorted(addresses)


def az_json(arguments):
    cli = shutil.which('az')
    if not cli:
        raise ValueError('Azure CLI is required')
    result = subprocess.run([cli, *arguments, '--output', 'json'],
                            capture_output=True, text=True, check=True, timeout=120)
    return json.loads(result.stdout)


def arm_get(resource_id, version):
    return az_json(['rest', '--method', 'get', '--url',
                    'https://management.azure.com' + resource_id + '?api-version=' + version])


def discover(subscription, environment, apps):
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', subscription):
        raise ValueError('Invalid subscription')
    if not re.fullmatch(r'cae-[a-z0-9-]+', environment) or not apps:
        raise ValueError('Environment and at least one existing app are required')
    root = f'/subscriptions/{subscription}/resourceGroups/rg-ecommerce-dev/providers/Microsoft.App/'
    expected_environment = root + 'managedEnvironments/' + environment
    addresses = set()
    for app in apps:
        if not re.fullmatch(r'ca-[a-z0-9-]+', app):
            raise ValueError('Invalid app name')
        response = arm_get(root + 'containerApps/' + app, '2026-01-01')
        properties = response['properties']
        owner = properties.get('environmentId') or properties.get('managedEnvironmentId')
        if (not isinstance(owner, str) or owner.lower() != expected_environment.lower()
                or properties.get('workloadProfileName') != 'Consumption'
                or properties.get('provisioningState') != 'Succeeded'):
            raise ValueError('App is not ready in the expected Consumption environment')
        addresses.update(public_ipv4(properties.get('outboundIpAddresses')))
    return public_ipv4(sorted(addresses))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subscription', required=True)
    parser.add_argument('--environment', default='cae-ecommerce-dev')
    parser.add_argument('--app', action='append', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        addresses = discover(args.subscription, args.environment, args.app)
        if not args.output.name.endswith('.auto.tfvars.json'):
            raise ValueError('Use an ignored auto.tfvars.json output')
        # Write only after complete successful readback; a failure preserves prior inputs.
        args.output.write_text(json.dumps({'database_aca_ipv4': addresses}, indent=2) + '\n', encoding='utf-8')
        print(f'D/7 discovered {len(addresses)} ACA outbound IPv4 addresses. Review a fresh Terraform plan; discovery does not change Azure.')
    except Exception:
        raise SystemExit('D/7 egress discovery failed; check Azure login, the ready app and its environment. No firewall change was made.')
