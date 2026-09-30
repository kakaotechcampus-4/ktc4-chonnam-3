"""텍스트에서 GitHub URL 정규식 파싱 → github.com/{owner}/{repo} → full_name.
포폴의 mentioned_repo_urls 원천. 포폴이 link 형태이고 그 링크 자체가 GitHub URL 이면
(프로필이든 레포든) 그것을 그대로 넣는다.

확정본 §3 user_documents / task-09

정규화 규칙은 spec/backend/features/documents.md 의 "GitHub URL 정규화" 절이다.
"""

import re
from urllib.parse import urlsplit

# URL 후보 하나를 통째로 잡는다: [스킴]호스트[:포트][/경로?query#hash].
# 후보를 먼저 자른 뒤 urlsplit 으로 진짜 hostname 을 검증한다. 그래서 다른 사이트 URL 의
# 경로·query·fragment 안에 있는 "github.com/..." 는 후보 안에 묻혀 따로 매치되지 않는다.
# 앞 문자 검사는 "a@github.com", "evil-github.com" 처럼 호스트 중간에서 시작하는 것을 막는다.
_URL_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9_.\-@])"
    r"(?:https?://)?"
    r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}"
    r"(?::\d+)?"
    r"(?:[/?#][^\s)>\]\"']*)?",
    re.IGNORECASE,
)

# gist.github.com 등 다른 하위 도메인은 저장소가 아니다.
_GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})

# owner 는 GitHub 규칙대로 영숫자와 하이픈만, 하이픈으로 시작하지 않는다.
_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
# repo 는 영숫자와 . _ - 를 허용한다. 뒤에 붙은 한글 조사 같은 글자는 버린다.
_REPO = re.compile(r"[A-Za-z0-9._-]+")

# github.com/<여기>/... 가 레포 소유자가 아닌 예약 경로들.
# 이 목록에 걸리면 owner/repo 로 취급하지 않는다.
_RESERVED_OWNERS = frozenset(
    {
        "about",
        "apps",
        "collections",
        "enterprise",
        "explore",
        "features",
        "join",
        "login",
        "logout",
        "marketplace",
        "notifications",
        "orgs",
        "pricing",
        "security",
        "settings",
        "sponsors",
        "topics",
        "trending",
        "users",
    }
)

# 레포 이름 자리에 올 수 없는 값. github.com/orgs/foo 같은 경로를 한 번 더 막는다.
_RESERVED_REPOS = frozenset({"settings", "followers", "following", "repositories"})


def _clean_repo(repo: str) -> str | None:
    """repo 조각에서 꼬리 문장부호와 .git 을 떼어낸다.

    입력: 경로의 repo 조각. 출력: 정리된 이름, 쓸 수 없으면 None.
    """
    matched = _REPO.match(repo)
    if matched is None:
        return None
    cleaned = matched.group().rstrip(".,;:!?")
    if cleaned.lower().endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    cleaned = cleaned.rstrip(".,;:!?")
    if not cleaned or cleaned in {".", ".."}:
        return None
    if cleaned.lower() in _RESERVED_REPOS:
        return None
    return cleaned


def _full_name_from_candidate(candidate: str) -> str | None:
    """URL 후보 하나가 GitHub 저장소면 owner/repo 를 돌려준다. 아니면 None."""
    target = candidate if "://" in candidate else f"https://{candidate}"
    try:
        parts = urlsplit(target)
        hostname = parts.hostname
    except ValueError:
        return None
    if hostname is None or hostname.lower() not in _GITHUB_HOSTS:
        return None

    segments = parts.path.split("/")
    # 경로는 "/" 로 시작하므로 segments[0] 은 빈 문자열이다.
    if len(segments) < 3:
        return None
    owner = segments[1]
    if _OWNER.fullmatch(owner) is None or owner.lower() in _RESERVED_OWNERS:
        return None
    repo = _clean_repo(segments[2])
    if repo is None:
        return None
    return f"{owner}/{repo}"


def normalize_github_url(url: str) -> str | None:
    """GitHub URL 하나를 owner/repo full_name 으로 정규화한다.

    입력: URL 문자열 (스킴은 있어도 없어도 된다).
    출력: "owner/repo", GitHub 레포 URL 이 아니면 None.

    hostname 이 github.com / www.github.com 인 URL 만 받는다. trailing slash, query,
    hash, .git 을 떼고 issue/pull/commit/blob/tree 하위 경로는 버린다.
    gist, GitLab, Bitbucket, 다른 사이트 URL 안에 끼어 있는 github.com 은 None 이다.
    """
    for match in _URL_CANDIDATE.finditer(url.strip()):
        full_name = _full_name_from_candidate(match.group())
        if full_name is not None:
            return full_name
    return None


def extract_github_full_names(text: str) -> list[str]:
    """텍스트 전체에서 GitHub 레포 full_name 을 뽑는다.

    입력: 추출된 문서 텍스트. 출력: "owner/repo" 목록. 중복을 제거하고 등장 순서를 지킨다.

    URL 형태만 인식한다 — "owner/repo" 텍스트만 있는 패턴은 제외한다
    (spec/backend/features/documents.md).
    """
    found: list[str] = []
    seen: set[str] = set()

    for match in _URL_CANDIDATE.finditer(text):
        full_name = _full_name_from_candidate(match.group())
        if full_name is None:
            continue
        key = full_name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(full_name)

    return found
