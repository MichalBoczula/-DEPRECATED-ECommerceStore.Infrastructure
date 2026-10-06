"""Show diagnostic locations/categories only; never raw detail or plan values."""
import json
import re
import sys
CATEGORIES={'Test assertion failed','Unknown condition value','Invalid index','Invalid value for input variable','Invalid value for variable','Unsupported attribute','Missing required argument','Unsupported argument',
    'Invalid body','Invalid configuration','Invalid resource type','Invalid resource type version','Error acquiring the state lock','Insufficient features blocks',
    'Preflight Validation: Invalid configuration','Invalid plan body configuration','Invalid state body configuration',
    'Invalid state body','Failed to retrieve resource','Failed to create/update resource','Error parsing ID'}
DEPLOYMENT = '--deployment' in sys.argv[2:]
FIELDS = ('candidate_suffix', 'candidate_sql_password', 'candidate_mongo_password')
RESOURCES = ('azurerm_mssql_server.database_candidate[0]', 'azapi_resource.sql_candidate[0]', 'azapi_resource.mongo_candidate[0]')
AZURE_CODES = ('AuthorizationFailed', 'LinkedAuthorizationFailed', 'MissingSubscriptionRegistration',
    'NoRegisteredProviderFound', 'InvalidApiVersionParameter', 'InvalidParameterValue',
    'InvalidResourceLocation', 'LocationNotAvailableForResourceType', 'SubscriptionNotRegistered',
    'RequestDisallowedByPolicy', 'QuotaExceeded', 'SkuNotAvailable', 'InvalidServerAdministratorPassword',
    'ResourceValidationFailed', 'InvalidResourceProperties', 'ResourceGroupNotFound', 'ParentResourceNotFound',
    'ResourceNotFound', 'InvalidResourceId', 'InvalidResourceName', 'InternalServerError')
found = False
for line in open(sys.argv[1],encoding='utf-8'):
    try: message=json.loads(line)
    except ValueError: continue
    if message.get('type') != 'diagnostic': continue
    diagnostic=message.get('diagnostic',{})
    if DEPLOYMENT and diagnostic.get('severity') != 'error': continue
    found = True
    location=diagnostic.get('range') or {}
    filename=location.get('filename','')
    number=location.get('start',{}).get('line',0)
    category=diagnostic.get('summary')
    if category not in CATEGORIES: category='Terraform deployment diagnostic' if DEPLOYMENT else 'Terraform test diagnostic'
    if re.fullmatch(r'[a-zA-Z0-9_./-]+',filename) and type(number) is int:
        print(f'{filename}:{number}: {category}',file=sys.stderr)
    else:
        print(category,file=sys.stderr)
    if DEPLOYMENT:
        context=(diagnostic.get('snippet') or {}).get('context','')
        for field in FIELDS:
            if context == f'variable "{field}"':
                print(f'Check environment input: {field}',file=sys.stderr)
        if diagnostic.get('address') in RESOURCES:
            print(f"Resource: {diagnostic['address']}",file=sys.stderr)
        detail=diagnostic.get('detail','')
        for code in AZURE_CODES:
            if re.search(r'\b'+code+r'\b',detail):
                print(f'Azure error category: {code}',file=sys.stderr)
        for field in ('properties.administrator.userName', 'properties.administrator.password', 'properties.compute.tier'):
            if field in detail:
                print(f'Field mentioned by provider: {field}',file=sys.stderr)
if DEPLOYMENT and not found:
    print('Terraform failed without a structured error diagnostic; no raw output published.',file=sys.stderr)
