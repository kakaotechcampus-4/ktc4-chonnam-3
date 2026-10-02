"""공통 입력 오류의 필드 안내와 인증 정보 비노출을 함께 검증한다."""

import httpx
from fastapi.exceptions import RequestValidationError

from app.main import create_app


async def test_validation_details_never_echo_input_context_or_raw_message() -> None:
    app = create_app()
    secret = "test-only-sensitive-token"

    @app.get("/validation-error")
    async def invalid_input() -> None:
        # 사용자 정의 validator의 메시지와 ctx에도 입력값이 포함될 수 있다.
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "postingUrl"),
                    "type": "value_error",
                    "msg": f"invalid {secret}",
                    "input": secret,
                    "ctx": {"error": ValueError(secret)},
                }
            ]
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/validation-error")

    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "no-store"
    assert secret not in response.text
    assert response.json()["error"]["details"]["fields"] == [
        {
            "field": "body.postingUrl",
            "type": "value_error",
            "message": "입력 형식을 확인해 주세요.",
        }
    ]
