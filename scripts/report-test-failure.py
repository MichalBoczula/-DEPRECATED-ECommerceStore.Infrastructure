"""Show diagnostic locations/categories only; never raw detail or plan values."""
import json
import re
import sys
CATEGORIES={'Test assertion failed','Unknown condition value','Invalid index','Invalid value for input variable','Unsupported attribute','Missing required argument','Unsupported argument'}
for line in open(sys.argv[1],encoding='utf-8'):
    try: message=json.loads(line)
    except ValueError: continue
    if message.get('type') != 'diagnostic': continue
    diagnostic=message.get('diagnostic',{})
    location=diagnostic.get('range') or {}
    filename=location.get('filename','')
    number=location.get('start',{}).get('line',0)
    if not re.fullmatch(r'[a-zA-Z0-9_./-]+',filename) or type(number) is not int: continue
    category=diagnostic.get('summary')
    if category not in CATEGORIES: category='Terraform test diagnostic'
    print(f'{filename}:{number}: {category}',file=sys.stderr)
