"""Partial contract validation; no runtime or compatibility claims."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / 'spec/shared/contracts'


def inline_refs(value, contracts, trail=()):
    """Inline local refs only, never retrieve remote URLs."""
    if isinstance(value, list):
        return [inline_refs(item, contracts, trail) for item in value]
    if not isinstance(value, dict):
        return value
    if '$ref' in value:
        reference = value['$ref']
        if not reference.startswith('./') or '#' in reference:
            raise ValueError(f'Unsupported ref in draft validator: {reference}')
        target = (contracts / reference).resolve()
        if not target.is_relative_to(contracts.resolve()) or not target.name.endswith('.schema.json'):
            raise ValueError('Contract ref escapes schema directory')
        if target in trail:
            raise ValueError('Cyclic draft schema ref')
        schema = json.loads(target.read_text(encoding='utf-8'))
        schema.pop('$schema', None)
        result = inline_refs(schema, contracts, trail + (target,))
        result.update({k: inline_refs(v, contracts, trail) for k, v in value.items() if k != '$ref'})
        return result
    return {key: inline_refs(item, contracts, trail) for key, item in value.items()}


def main():
    try:
        from jsonschema import Draft202012Validator
        from openapi_spec_validator import validate
    except ImportError:
        print('미실행: python3 -m pip install -r .claude/scripts/requirements-checks.txt 필요', file=sys.stderr)
        return 2
    try:
        schemas = {}
        for path in sorted(CONTRACTS.glob('*.schema.json')):
            schema = json.loads(path.read_text(encoding='utf-8'))
            Draft202012Validator.check_schema(schema)
            schemas[path.name] = Draft202012Validator(schema)
        if not schemas:
            raise ValueError('No contract schemas found')
        # JSON syntax is a YAML-compatible subset used by this draft .yaml.
        document = json.loads((CONTRACTS / 'openapi.yaml').read_text(encoding='utf-8'))
        validate(inline_refs(copy.deepcopy(document), CONTRACTS))
        cases = json.loads((CONTRACTS / 'examples/validation-cases.json').read_text(encoding='utf-8'))
        if not cases:
            raise ValueError('No validation fixtures found')
        for case in cases:
            valid = schemas[case['schema']].is_valid(case['data'])
            if valid != case['valid']:
                raise ValueError(f'Fixture outcome mismatch: {case["name"]}')
        print(f'PASS: {len(schemas)} schemas, partial OpenAPI, {len(cases)} positive/negative fixtures')
        print('LIMIT: Runtime, TypeScript matching, full API coverage and compatibility are not verified.')
        return 0
    except Exception as exc:
        print(f'FAIL: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
