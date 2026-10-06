"""CamelModel - alias_generator=to_camel, populate_by_name, from_attributes.

docs/layer-rules.md 4절 / task-04

API schema 는 전부 이걸 상속한다. 요구사항은 세 가지다 (layer-rules 직렬화 절).

- response 에 snake_case key 가 새지 않는다
- request body 는 camelCase 를 기준으로 받는다
- DB column 이름을 그대로 API 에 노출하지 않는다
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """API request/response 공통 base.

    Python 필드는 snake_case 로 두고 직렬화 이름만 camelCase 로 바꾼다.
    DB column 과 API 필드 이름이 다를 때는 필드 이름 자체를 API 기준으로 정하고
    service 계층에서 변환한다 — 경계 매핑 레이어를 따로 두지 않는다.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        # 내부 코드가 snake_case 이름으로 생성할 수 있게 둔다.
        # 직렬화는 model_dump(by_alias=True) 로 camelCase 가 된다.
        populate_by_name=True,
        # ORM 객체에서 바로 만들 수 있게 한다 (service -> schema).
        from_attributes=True,
        # 계약에 없는 키를 조용히 받아들이지 않는다.
        extra="forbid",
    )


class CamelResponse(CamelModel):
    """응답 전용 base.

    FastAPI response_model 경로는 response_model_by_alias 기본값(True)으로 이미 camelCase 다.
    이 base 는 그 경로 밖 — 일반 Python 코드의 model_dump()·model_dump_json() —
    에서도 by_alias 를 넘기지 않고 기본으로 camelCase 가 나오게 하려고 둔다.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
        # 응답은 항상 alias(camelCase) 로 직렬화한다.
        serialize_by_alias=True,
    )
