import httpx
import pytest
from pydantic import SecretStr

from app.integrations.vision.elice import EliceVisionClient, EliceVisionSettings, VisionError


def settings(**overrides):
    return EliceVisionSettings(
        base_url="https://unit.mlapi.run/model",
        api_key=SecretStr("vision-secret"),
        poll_interval_seconds=0,
        **overrides,
    )


@pytest.mark.asyncio
async def test_document_submission_polling_and_layout_preservation():
    requests = []
    raw = {
        "page_count": 1,
        "pages": [
            {
                "elements": [
                    {"label": "paragraph", "content": "구현한 내용", "coordinate": [1, 2, 30, 40]},
                    {"label": "image", "description": "모델이 생성한 이미지 설명"},
                ]
            }
        ],
    }

    def respond(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer vision-secret"
        if request.method == "POST":
            assert request.url.path == "/model/v1/documents"
            assert b'name="document"' in request.content
            return httpx.Response(200, json={"job_id": "job-1", "status": "queued"})
        assert request.url.path == "/model/v1/jobs/job-1"
        return httpx.Response(200, json={"status": "succeeded", "result": raw})

    result = await EliceVisionClient(settings(), httpx.MockTransport(respond)).extract(
        b"%PDF-1.7 sample", "application/pdf"
    )
    assert result.job_id == "job-1"
    assert result.page_count == 1
    assert result.blocks[0].page == 1
    assert result.blocks[0].element_index == 0
    assert result.blocks[0].content == "구현한 내용"
    assert result.blocks[0].coordinate == [1, 2, 30, 40]
    assert result.blocks[1].content is None
    assert result.blocks[1].description == "모델이 생성한 이미지 설명"
    assert result.raw_result == raw
    assert len(requests) == 2


@pytest.mark.parametrize("suffix", ["", "/", "/v1", "/v1/"])
async def test_base_normalization_keeps_namespace_and_one_api_version(suffix):
    seen = []

    def respond(request):
        seen.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "normalized"})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "result": {
                    "pages": [{"elements": [{"label": "text", "content": "synthetic"}]}],
                },
            },
        )

    config = EliceVisionSettings(
        base_url="https://unit.mlapi.run/model" + suffix,
        api_key=SecretStr("vision-secret"),
        poll_interval_seconds=0,
    )
    await EliceVisionClient(config, httpx.MockTransport(respond)).extract(b"image", "image/png")
    assert seen == ["/model/v1/documents", "/model/v1/jobs/normalized"]


@pytest.mark.parametrize("coordinate", [None, {"x": 1, "y": 2}])
async def test_live_bounding_box_field_is_preserved_without_overriding_coordinate(coordinate):
    box = [10.5, 20, 300, 400]

    def respond(request):
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "actual-shape"})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "result": {
                    "pages": [
                        {
                            "elements": [
                                {
                                    "label": "figure",
                                    "description": "Synthetic diagram",
                                    "coordinate": coordinate,
                                    "bounding_box": box,
                                }
                            ],
                        }
                    ]
                },
            },
        )

    result = await EliceVisionClient(settings(), httpx.MockTransport(respond)).extract(
        b"image", "image/png"
    )
    assert result.blocks[0].coordinate == (coordinate if coordinate is not None else box)
    assert result.raw_result["pages"][0]["elements"][0]["bounding_box"] == box


@pytest.mark.asyncio
async def test_poll_count_is_bounded_without_duplicate_submission():
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "job-1", "status": "queued"})
        return httpx.Response(200, json={"status": "running"})

    with pytest.raises(VisionError, match="poll_limit"):
        await EliceVisionClient(settings(max_polls=2), httpx.MockTransport(respond)).extract(
            b"%PDF-1.7", "application/pdf"
        )
    assert [r.method for r in requests] == ["POST", "GET", "GET"]


@pytest.mark.parametrize(
    "body",
    [
        {"status": "succeeded", "result": {}},
        {"status": "failure", "error": "vision-secret"},
        {"result": {}},
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_failed_job_never_returns_success(body):
    def respond(request):
        return httpx.Response(200, json={"job_id": "job-1"} if request.method == "POST" else body)

    with pytest.raises(VisionError) as got:
        await EliceVisionClient(settings(), httpx.MockTransport(respond)).extract(
            b"%PDF-1.7", "application/pdf"
        )
    assert "vision-secret" not in str(got.value)


@pytest.mark.asyncio
async def test_unsafe_job_id_is_not_followed():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"job_id": "../../private"})

    with pytest.raises(VisionError, match="invalid_response"):
        await EliceVisionClient(settings(), httpx.MockTransport(respond)).extract(
            b"%PDF-1.7", "application/pdf"
        )
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_limits_and_unsupported_input_fail_before_network():
    requests = []
    client = EliceVisionClient(
        settings(max_file_bytes=3), httpx.MockTransport(lambda r: requests.append(r))
    )
    with pytest.raises(VisionError, match="document_too_large"):
        await client.extract(b"%PDF-1.7", "application/pdf")
    with pytest.raises(VisionError, match="unsupported_document"):
        await client.extract(b"abc", "text/plain")
    assert requests == []


@pytest.mark.parametrize(
    "base_url",
    [
        "http://unit.mlapi.run/model",
        "https://name:vision-secret@unit.mlapi.run/model",
        "https://unit.mlapi.run/model?key=vision-secret",
    ],
)
def test_base_url_rejects_credentials_or_query_without_leaking(base_url):
    with pytest.raises(ValueError) as got:
        EliceVisionSettings(base_url=base_url, api_key=SecretStr("secret"))
    assert "vision-secret" not in str(got.value)
