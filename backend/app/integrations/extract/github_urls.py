"""텍스트에서 GitHub URL 정규식 파싱 → github.com/{owner}/{repo} → full_name.
포폴의 mentioned_repo_urls 원천. 포폴이 link 형태이고 그 링크 자체가 GitHub URL 이면
(프로필이든 레포든) 그것을 그대로 넣는다.

확정본 §3 user_documents / task-09

정규화 규칙은 spec/backend/features/documents.md 의 "GitHub URL 정규화" 절이다.
"""

import re

# (?<![\w.-]) 가 gist.github.com 을 막는다 — 앞에 점이 있으면 매치하지 않는다.
# owner 는 GitHub 규칙대로 영숫자와 하이픈만, 하이픈으로 시작하지 않는다.
# repo 는 영숫자와 . _ - 를 허용한다.
_GITHUB_URL = re.compile(
    r"(?<![\w.-])"
    r"(?:https?://)?"
    r"(?:www\.)?"
    r"github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/"
    r"(?P<repo>[A-Za-z0-9._-]+)"
    # issue, pull, commit, blob, tree 같은 하위 경로와 query/hash 는 버린다.
    r"(?P<rest>[/?#][^\s)>\]\"']*)?",
    re.IGNORECASE,
)

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

    입력: 매치된 repo 문자열. 출력: 정리된 이름, 쓸 수 없으면 None.
    """
    cleaned = repo.rstrip(".,;:!?")
    if cleaned.lower().endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    cleaned = cleaned.rstrip(".,;:!?")
    if not cleaned or cleaned in {".", ".."}:
        return None
    if cleaned.lower() in _RESERVED_REPOS:
        return None
    return cleaned


def normalize_github_url(url: str) -> str | None:
    """GitHub URL 하나를 owner/repo full_name 으로 정규화한다.

    입력: URL 문자열 (스킴은 있어도 없어도 된다).
    출력: "owner/repo", GitHub 레포 URL 이 아니면 None.

    trailing slash, query, hash, .git 을 떼고 issue/pull/commit/blob/tree 하위 경로는 버린다.
    gist, GitLab, Bitbucket 은 None 이다.
    """
    match = _GITHUB_URL.search(url.strip())
    if match is None:
        return None
    # search 가 문자열 중간부터 잡았으면 URL 하나를 넘긴 것이 아니다.
    owner = match.group("owner")
    if owner.lower() in _RESERVED_OWNERS:
        return None
    repo = _clean_repo(match.group("repo"))
    if repo is None:
        return None
    return f"{owner}/{repo}"


def extract_github_full_names(text: str) -> list[str]:
    """텍스트 전체에서 GitHub 레포 full_name 을 뽑는다.

    입력: 추출된 문서 텍스트. 출력: "owner/repo" 목록. 중복을 제거하고 등장 순서를 지킨다.

    URL 형태만 인식한다 — "owner/repo" 텍스트만 있는 패턴은 제외한다
    (spec/backend/features/documents.md).
    """
    found: list[str] = []
    seen: set[str] = set()

    for match in _GITHUB_URL.finditer(text):
        owner = match.group("owner")
        if owner.lower() in _RESERVED_OWNERS:
            continue
        repo = _clean_repo(match.group("repo"))
        if repo is None:
            continue
        full_name = f"{owner}/{repo}"
        key = full_name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(full_name)

    return found
