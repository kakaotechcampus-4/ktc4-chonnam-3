"""공통 enum·error reason의 구현 예정 경계.
API 필드·enum은 공통 OpenAPI와 오류 계약을 따른다. DB 상태와 API 상태가 다른 경우
명시적으로 매핑한다 (예: DB partial → FE failed). Python/DB 이름은 snake_case다.

docs/layer-rules.md 3절 · docs/error-reasons.md / task-04
"""
