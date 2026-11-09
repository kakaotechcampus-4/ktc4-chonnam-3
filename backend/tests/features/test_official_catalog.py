"""공식 도메인과 실제 질의 관련성·버전·요청 절을 구분한다."""

import hashlib
from dataclasses import replace

import pytest

from app.integrations.search.tavily import WebSource


def source(content, *, version="3.12", language="en", limitations=()):
    prefix = "" if language == "en" else f"{language}/"
    return WebSource(
        f"https://docs.python.org/{prefix}{version}/library/asyncio-task.html",
        f"Python {version} Coroutines and Tasks",
        content,
        "extracted_page",
        "2026-11-08T00:00:00+00:00",
        hashlib.sha256(content.encode()).hexdigest(),
        limitations=limitations,
    )


def python_entry():
    from app.features.knowledge.official_catalog import load_catalog

    return next(item for item in load_catalog() if item.catalog_key == "python-3.12-task-groups")


def test_existing_etc_domain_order_preserves_query_cache_keys():
    from app.features.interview.external_knowledge import _cache_key
    from app.features.knowledge.official_catalog import scope_domains

    legacy_domains = ("elice.io", "developer.mozilla.org", "docs.python.org")
    assert _cache_key("Redis architecture", scope_domains("etc")) == _cache_key(
        "Redis architecture", legacy_domains
    )


def test_actual_markdown_link_heading_keeps_original_text_and_section_coordinates():
    from app.features.knowledge.official_catalog import prepare_snapshot

    page = (
        '# Coroutines and Tasks[¶](#coroutines-and-tasks "Link to this heading")\n'
        '## [Task Groups](#id6)[¶](#task-groups "Link to this heading")\n'
        "Synthetic TaskGroup passage.\n"
        '## [Sleeping](#id7)[¶](#sleeping "Link to this heading")\nOther.'
    )
    item = prepare_snapshot(python_entry(), source(page, limitations=("content_truncated",)))
    assert item.content == "\n".join(page.splitlines()[1:3])
    assert (item.start_line, item.end_line) == (2, 3)
    assert item.page_content == page


def test_heading_link_target_cannot_replace_the_requested_visible_title():
    from app.features.knowledge.official_catalog import OfficialSourceError, prepare_snapshot

    page = "## [Unrelated title](#task-groups)\nTaskGroup unrelated section."
    with pytest.raises(OfficialSourceError, match="requested_section_missing"):
        prepare_snapshot(python_entry(), source(page))


def test_catalog_has_all_service_domains_and_general_with_explicit_access_status():
    from app.features.knowledge.official_catalog import load_catalog

    entries = load_catalog()
    assert {category for item in entries for category in item.domain_categories} == {
        "finance",
        "game",
        "travel",
        "shopping",
        "medical",
        "mobility",
        "etc",
        "general",
    }
    assert len({item.catalog_key for item in entries}) == len(entries)
    assert all(item.verified_at and item.url.startswith("https://") for item in entries)
    assert any(
        item.availability != "public_verified"
        for item in entries
        if "travel" in item.domain_categories
    )


def test_general_python_query_matches_in_financial_domain_without_replacing_category():
    from app.features.knowledge.official_catalog import matching_entries

    entries = matching_entries("Python 3.12 asyncio TaskGroup cancellation", "finance")
    assert [item.catalog_key for item in entries] == ["python-3.12-task-groups"]


def test_wrong_version_and_topic_do_not_match_catalog_just_because_domain_is_official():
    from app.features.knowledge.official_catalog import matching_entries

    assert matching_entries("Python 3.10 asyncio TaskGroup", "etc") == ()
    assert matching_entries("Python 3.12 CSV parsing", "etc") == ()


def test_snapshot_preserves_exact_section_and_page_coordinates_without_toc_substitution():
    from app.features.knowledge.official_catalog import prepare_snapshot

    page = (
        "# Coroutines\n* [Task Groups](#task-groups)\n## Task Groups\n"
        "TaskGroup cancels tasks.\n### Example\nawait task\n## Sleeping\nSleep."
    )
    item = prepare_snapshot(python_entry(), source(page))
    assert item.content == "## Task Groups\nTaskGroup cancels tasks.\n### Example\nawait task"
    assert (item.start_line, item.end_line) == (3, 6)
    assert item.page_content == page
    assert item.content_hash == hashlib.sha256(item.content.encode()).hexdigest()
    assert item.page_content_hash == hashlib.sha256(page.encode()).hexdigest()
    assert item.url.endswith("asyncio-task.html")


@pytest.mark.parametrize(
    "page,limitations,reason",
    [
        ("# Contents\n* [Task Groups](#task-groups)\nunrelated", (), "requested_section_missing"),
        (
            "# Coroutines\n## Task Groups\nTaskGroup partial",
            ("content_truncated",),
            "requested_section_incomplete",
        ),
        (
            "# Coroutines\n```md\n## Task Groups\nTaskGroup example\n```",
            (),
            "requested_section_missing",
        ),
        ("# Coroutines\n## Task Groups\n\n## Sleeping\nOther", (), "requested_section_empty"),
    ],
)
def test_missing_or_truncated_requested_section_is_not_a_snapshot(page, limitations, reason):
    from app.features.knowledge.official_catalog import OfficialSourceError, prepare_snapshot

    with pytest.raises(OfficialSourceError, match=reason):
        prepare_snapshot(python_entry(), source(page, limitations=limitations))


def test_complete_section_before_truncated_page_end_is_kept_with_limitation():
    from app.features.knowledge.official_catalog import prepare_snapshot

    page = "## Task Groups\nTaskGroup details.\n## Sleeping\ntruncated elsewhere"
    item = prepare_snapshot(python_entry(), source(page, limitations=("content_truncated",)))
    assert item.content == "## Task Groups\nTaskGroup details."
    assert "content_truncated" in item.limitations


@pytest.mark.parametrize(
    "candidate,reason",
    [
        (source("## Task Groups\nTaskGroup", version="3.10"), "source_version_mismatch"),
        (source("## Task Groups\nTaskGroup", language="fr"), "source_language_mismatch"),
        (
            replace(source("## Task Groups\nTaskGroup"), content_hash="0" * 64),
            "source_hash_mismatch",
        ),
    ],
)
def test_catalog_snapshot_rejects_different_version_language_or_tampered_original(
    candidate, reason
):
    from app.features.knowledge.official_catalog import OfficialSourceError, prepare_snapshot

    with pytest.raises(OfficialSourceError, match=reason):
        prepare_snapshot(python_entry(), candidate)


def test_live_search_relevance_requires_requested_api_identifiers_not_only_python_domain():
    from app.features.knowledge.official_catalog import source_matches_query

    query = (
        "Python 3.12 asyncio TaskGroup cancellation CancelledError "
        "KeyboardInterrupt SystemExit ExceptionGroup"
    )
    valid = source(
        "TaskGroup cancellation handles CancelledError KeyboardInterrupt SystemExit ExceptionGroup"
    )
    assert source_matches_query(query, valid)[0]
    assert not source_matches_query(query, source("CancelledError and TimeoutError"))[0]
    assert not source_matches_query(query, source(valid.content, version="3.10"))[0]
    assert not source_matches_query(query + " english", source(valid.content, language="fr"))[0]


def test_generic_live_source_must_have_actual_query_terms():
    from app.features.knowledge.official_catalog import source_matches_query

    unrelated = replace(source("Official website navigation"), url="https://elice.io/reference")
    related = replace(unrelated, content="Redis session architecture details")
    assert not source_matches_query("Redis session architecture", unrelated)[0]
    assert source_matches_query("Redis session architecture", related)[0]


def test_http_status_and_header_are_concrete_topics_even_without_other_query_words():
    from app.features.knowledge.official_catalog import source_matches_query

    candidate = replace(
        source("HTTP 429 can provide Retry-After."),
        url="https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429",
    )
    assert source_matches_query("HTTP 429 Retry-After", candidate)[0]


async def test_unavailable_optional_catalog_leaves_search_fallback_available(monkeypatch):
    from app.features.knowledge.official_snapshots import load_shared_sources

    def unavailable():
        raise OSError("catalog is unavailable")

    monkeypatch.setattr("app.features.knowledge.official_catalog.load_catalog", unavailable)
    result = await load_shared_sources(None, "Python TaskGroup", "etc", max_age_seconds=3600)
    assert result.sources == ()
    assert result.limitations == ("official_catalog_unavailable",)


@pytest.mark.parametrize(
    "query,body",
    [
        ("Spring 6.1 transaction isolation", "Python transaction isolation details"),
        ("Spring Boot 3.3 transaction isolation", "Spring Boot 3.2 transaction isolation details"),
        ("React 19.0 state update", "Python state update details"),
        ("Kubernetes 1.30 pod retry", "Python retry details"),
        ("Java 17 transaction isolation", "JavaScript transaction isolation details"),
        ("Spring 6 transaction isolation", "Spring 5 transaction isolation details"),
    ],
)
def test_other_framework_query_cannot_adopt_shared_generic_words_on_python_page(query, body):
    from app.features.knowledge.official_catalog import source_matches_query

    assert not source_matches_query(query, source(body))[0]
