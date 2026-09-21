"""계약 일부만 검증하며 런타임 동작이나 호환성은 보장하지 않는다."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / 'spec/shared/contracts'


def load_yaml_document(path):
    """임의 객체 생성을 허용하지 않고 YAML 매핑을 읽는다."""
    from yaml import safe_load

    document = safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(document, dict):
        raise ValueError(f'Expected YAML mapping: {path}')
    return document


def inline_refs(value, contracts, trail=()):
    """로컬 참조만 인라인으로 풀고 원격 URL은 조회하지 않는다."""
    if isinstance(value, list):
        return [inline_refs(item, contracts, trail) for item in value]
    if not isinstance(value, dict):
        return value
    if '$ref' in value:
        reference = value['$ref']
        if reference.startswith('#/'):
            # 내부 참조는 원본 OpenAPI 문서를 기준으로 해석해야 한다.
            return {
                key: item if key == '$ref' else inline_refs(item, contracts, trail)
                for key, item in value.items()
            }
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
        import yaml  # noqa: F401 - 설정 오류를 명확히 알리기 위한 의존성 사전 확인
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
        document = load_yaml_document(CONTRACTS / 'openapi.yaml')
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
