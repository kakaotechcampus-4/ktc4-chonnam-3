import pytest

from app.integrations.jd.base import UnsupportedSiteError
from app.integrations.jd.generic import GenericAdapter
from app.integrations.jd.resolver import resolve_adapter
from app.integrations.jd.wanted import WantedAdapter


def test_wanted_host_resolves_to_wanted_adapter():
    adapter = resolve_adapter("https://www.wanted.co.kr/wd/123456")
    assert isinstance(adapter, WantedAdapter)


def test_wanted_host_without_www_also_resolves():
    adapter = resolve_adapter("https://wanted.co.kr/wd/123456")
    assert isinstance(adapter, WantedAdapter)


def test_unknown_host_resolves_to_generic_adapter():
    adapter = resolve_adapter("https://www.saramin.co.kr/zf_user/jobs/view/123")
    assert isinstance(adapter, GenericAdapter)


def test_url_without_host_raises_unsupported():
    with pytest.raises(UnsupportedSiteError):
        resolve_adapter("not-a-url")
