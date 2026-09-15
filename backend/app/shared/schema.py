"""CamelModel - alias_generator=to_camel, populate_by_name, from_attributes.

docs/layer-rules.md 4절 / task-04
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """API request/response 공통 base. 응답에 snake_case key 가 새지 않게 한다."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        ser_json_timedelta="float",
    )
