"""page 쿼리 파라미터.

docs/layer-rules.md / task-04

Sprint 1 의 페이지네이션은 GET /analysis-runs/{runId}/candidates?page=N 하나뿐이다.
응답은 offset/total 을 담지 않고 {"repositories": [...]} 만 돌려준다 (openapi CandidatesResponse).
cursor·total count 가 필요해지면 그때 계약과 함께 넓힌다.
"""

from pydantic import Field

from app.shared.schema import CamelModel


class PageParams(CamelModel):
    """1부터 시작하는 page 번호. 입력: page. 출력: 검증된 PageParams."""

    page: int = Field(ge=1, description="1부터 시작한다. openapi 에서 required 다.")
