"""텍스트에서 GitHub URL 정규식 파싱 → github.com/{owner}/{repo} → full_name.

포폴의 mentioned_repo_urls 원천. 포폴이 link 형태이고 그 링크 자체가 GitHub URL 이면
(프로필이든 레포든) 그것을 그대로 넣는다.

full_name 매칭 실패(남의 레포·private·삭제·오타)는 정상 상황이다.

확정본 §3 user_documents / task-09
"""

import re

_URL = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/(?P<owner>[\w.-]+)(?:/(?P<repo>[\w.-]+))?",
    re.IGNORECASE,
)
#: owner 자리에 올 수 있지만 사용자/레포가 아닌 경로들.
_RESERVED = {"orgs", "topics", "collections", "sponsors", "settings", "features", "about"}
_TRAILING = re.compile(r"(?:\.git)?[/#?].*$|(?:\.git)$")


def extract_full_names(text: str) -> list[str]:
    """텍스트에서 `owner/repo` 목록을 순서대로, 중복 없이 뽑는다."""
    names: list[str] = []
    for match in _URL.finditer(text or ""):
        full_name = _to_full_name(match.group("owner"), match.group("repo"))
        if full_name and full_name not in names:
            names.append(full_name)
    return names


def normalize_repo_url(url: str) -> str | None:
    """레포 URL 하나를 `owner/repo` 로 정규화한다. 프로필 URL 이면 None."""
    match = _URL.match(url.strip())
    if not match:
        return None
    return _to_full_name(match.group("owner"), match.group("repo"))


def _to_full_name(owner: str | None, repo: str | None) -> str | None:
    if not owner or not repo:
        return None
    owner_clean = owner.strip()
    repo_clean = _TRAILING.sub("", repo.strip())
    if not repo_clean or owner_clean.lower() in _RESERVED:
        return None
    return f"{owner_clean}/{repo_clean}"
