# 공통 계약 — 전환 초안

## 현재 범위
- openapi.yaml: GET /api/me의 200·401 응답만 옮긴 부분 계약.
- me-response.schema.json: 기존 FE MeResponse와 일치하는 응답 구조.
- api-error.schema.json: 기존 FE ApiError와 BE 에러 봉투의 공통 구조.
- 기존 타입에 없는 제약을 몰래 추가하지 않기 위해 추가 속성을 허용한다. 정확한 키 집합 검사는 기존 BE 계약 테스트에서 별도 검증한다.
- 인증 쿠키 이름, OAuth 세부 흐름, SSE/WS, 다른 API는 이 초안의 범위 밖이다.
- 이 스키마는 현재 서버의 구현 완료를 의미하지 않는다.

## 변경 절차
1. frontend/docs/api-spec.md, frontend/src/types/api.ts, backend/docs/api-spec.md와 영향 범위를 비교.
2. 변경 전후 필드·required·nullable·enum·상태코드를 PR에 작성.
3. 계약·용어에 지속적인 영향이 있으면 spec/shared/decisions/에 Proposed 결정 작성.
4. FE·BE·AI가 관련 소비 코드·테스트·배포 순서 검토. 검토 상태를 migration.md에 기록.
5. 스키마·예시·구현·테스트 갱신. 코드 미구현이면 별도 표시.
6. 모든 대상이 이관된 항목만 기준 계약으로 승격. 기존 명세는 새 원본 링크로 전환.

## 검증
프로젝트 루트, Python 3.12 권장:
```bash
python3 -m pip install -r .claude/scripts/requirements-checks.txt
python3 .claude/scripts/check_contracts.py
```
OpenAPI 문서 및 JSON Schema 형식, 참조, 정상·오류 fixture를 검사한다.
실제 API·TS 타입·LLM 품질·하위 호환성을 자동 보증하지 않는다. /contract-check에서 변경 diff와 구현 테스트도 확인한다.
