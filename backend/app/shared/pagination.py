"""page 쿼리 파라미터.

docs/layer-rules.md / task-04

GET /analysis-runs/{runId}/candidates 의 page 쿼리 파라미터용이다 (openapi 에서 required).
GET /me/interviews 는 page·size 가 optional + default 라 이 클래스를 그대로 쓰지 않는다.
candidates 응답은 offset/total 을 담지 않고 {"repositories": [...]} 만 돌려준다
(openapi CandidatesResponse).
cursor·total count 가 필요해지면 그때 계약과 함께 넓힌다.
"""

from pydantic import Field

from app.shared.schema import CamelModel


class PageParams(CamelModel):
    """1부터 시작하는 page 번호. 입력: page. 출력: 검증된 PageParams."""

    page: int = Field(ge=1, description="1부터 시작한다. openapi 에서 required 다.")
