"""정상 빈 값과 수집 실패를 구분해 이전 저장 자료를 지우지 않게 한다."""

import httpx
import pytest

from app.integrations.github.base import RepoDetail, RepoSummary
from app.integrations.github.client import GithubClient

REPO = RepoSummary(github_repo_id=1, name="repo", full_name="user/repo", default_branch="main")
FIELDS = frozenset(
    {
        "languages",
        "readme_text",
        "readme_truncated",
        "head_sha",
        "commit_count",
        "user_commit_count",
    }
)


async def _detail(overrides: dict[str, httpx.Response]) -> RepoDetail:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/languages"):
            key, payload = "languages", {}
        elif request.url.path.endswith("/readme"):
            key, payload = "readme", {"encoding": "base64", "content": ""}
        elif request.url.path.endswith("/commits/main"):
            key, payload = "head_sha", {"sha": "a" * 40}
        else:
            key = "user_commit_count" if "author" in request.url.params else "commit_count"
            payload = []
        return overrides.get(key, httpx.Response(200, json=payload))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        return await GithubClient("test-token", client=http).fetch_repo_detail(REPO, login="user")


async def test_successful_empty_values_are_observed() -> None:
    detail = await _detail({})

    assert getattr(detail, "collected_fields", None) == FIELDS
    assert detail.languages == {} and detail.readme_text == ""
    assert detail.commit_count == detail.user_commit_count == 0
    assert detail.errors == []


@pytest.mark.parametrize(
    ("endpoint", "missing_fields"),
    [
        ("languages", {"languages"}),
        ("readme", {"readme_text", "readme_truncated"}),
        ("head_sha", {"head_sha"}),
        ("commit_count", {"commit_count"}),
        ("user_commit_count", {"user_commit_count"}),
    ],
)
async def test_only_failed_fields_are_unobserved(endpoint, missing_fields) -> None:
    detail = await _detail({endpoint: httpx.Response(503)})

    assert getattr(detail, "collected_fields", None) == FIELDS - missing_fields
    assert detail.errors == ["repo_unreachable"]


@pytest.mark.parametrize(("status", "error"), [(401, "token_invalid"), (429, "rate_limited")])
@pytest.mark.parametrize(
    ("endpoint", "observed"),
    [
        ("languages", set()),
        ("readme", {"languages"}),
        ("head_sha", {"languages", "readme_text", "readme_truncated"}),
        ("commit_count", {"languages", "readme_text", "readme_truncated", "head_sha"}),
        ("user_commit_count", FIELDS - {"user_commit_count"}),
    ],
)
async def test_stop_retains_only_fields_observed_before_failure(status, error, endpoint, observed):
    detail = await _detail({endpoint: httpx.Response(status)})

    assert getattr(detail, "collected_fields", None) == observed
    assert detail.errors == [error]


async def test_readme_404_is_observed_absence() -> None:
    detail = await _detail({"readme": httpx.Response(404)})

    assert getattr(detail, "collected_fields", None) == FIELDS
    assert detail.readme_text is None and not detail.readme_truncated
    assert detail.errors == ["no_readme"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"content": 12},
        {"encoding": "base64", "content": "a"},
        {"encoding": "base64", "content": "!!!!"},
    ],
)
async def test_invalid_readme_is_not_observed_absence(payload) -> None:
    detail = await _detail({"readme": httpx.Response(200, json=payload)})

    assert getattr(detail, "collected_fields", None) == FIELDS - {"readme_text", "readme_truncated"}
    assert detail.errors == ["no_readme"]


@pytest.mark.parametrize(
    ("field", "payload"),
    [("languages", []), ("commit_count", {}), ("user_commit_count", {})],
)
async def test_invalid_payload_is_not_observed_as_an_empty_result(field, payload) -> None:
    detail = await _detail({field: httpx.Response(200, json=payload)})

    assert detail.collected_fields == FIELDS - {field}
    assert detail.errors == ["repo_unreachable"]


@pytest.mark.parametrize(
    "payload",
    [
        {"Python": "invalid"},
        {"Python": True},
        {"Python": -1},
        {"Python": 1.5},
        {"Python": None},
        {"Python": 100, "Java": "invalid"},
    ],
)
async def test_invalid_language_bytes_fail_the_field_instead_of_becoming_empty(payload) -> None:
    detail = await _detail({"languages": httpx.Response(200, json=payload)})

    assert detail.collected_fields == FIELDS - {"languages"}
    assert detail.languages == {}
    assert detail.errors == ["repo_unreachable"]


async def test_zero_language_bytes_remain_an_observed_value() -> None:
    detail = await _detail({"languages": httpx.Response(200, json={"Python": 0, "Java": 100})})

    assert detail.collected_fields == FIELDS
    assert detail.languages == {"Python": 0, "Java": 100}
    assert detail.errors == []


async def test_wrapped_base64_is_still_a_successful_readme() -> None:
    detail = await _detail(
        {"readme": httpx.Response(200, json={"encoding": "base64", "content": "YWJj\nZGVm\n"})}
    )

    assert detail.readme_text == "abcdef"
    assert detail.collected_fields == FIELDS
    assert detail.errors == []


@pytest.mark.parametrize("field", ["commit_count", "user_commit_count"])
async def test_indeterminate_count_is_not_observed(field) -> None:
    detail = await _detail(
        {
            field: httpx.Response(
                200,
                json=[{"sha": "a" * 40}],
                headers={
                    "link": '<https://api.github.com/repos/user/repo/commits?page=2>; rel="next"'
                },
            )
        }
    )

    assert getattr(detail, "collected_fields", None) == FIELDS - {field}
    assert getattr(detail, field) is None
    assert detail.errors == []


@pytest.mark.parametrize("sha", [None, "", "invalid", "g" * 40])
async def test_missing_or_invalid_sha_is_not_observed(sha) -> None:
    detail = await _detail({"head_sha": httpx.Response(200, json={"sha": sha})})

    assert getattr(detail, "collected_fields", None) == FIELDS - {"head_sha"}
