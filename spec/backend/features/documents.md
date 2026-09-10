# 문서 Preview

상태: Sprint 1 FIX.

## 목적

문서는 Sprint 1에서 보조 신호다. 자소서/포트폴리오 claim을 추출하지 않고, 텍스트와 GitHub URL만 저장한다. `document_claims` 테이블은 Sprint 1 migration에 포함하지만 row는 생성하지 않는다.

## API

`POST /documents/preview`

- 파일 업로드.
- 텍스트 추출.
- GitHub URL 추출/정규화.
- 길이 초과 시 LLM 없이 JD keyword, GitHub URL 주변 문장, 헤딩/프로젝트 섹션 중심으로 축약.
- `documentId`와 preview 상태를 반환한다.

## 지원 형식

- `.pdf`: 텍스트 레이어가 있는 PDF만 지원. 스캔 이미지 PDF는 추출 실패로 처리한다.
- `.docx`
- `.txt`
- `.md`

미지원:

- `.hwp`
- 이미지 파일
- `.ppt`, `.pptx`

제한:

- 파일 최대 크기: 10MB.
- 파일 바이너리는 Sprint 1에서 저장하지 않는다.
- DB에는 filename, MIME type, size, extracted_text, extracted_github_urls, extract_status, truncation 여부만 저장한다.
- `document_claims` row 생성은 Sprint 2에서 자소서/포트폴리오 claim 추출을 함께 구현할 때 시작한다.

## 상태

- `succeeded`: 텍스트/GitHub URL 추출 성공.
- `partial`: 일부 텍스트만 추출 또는 길이 초과 축약.
- `failed`: 추출 실패.

문서 추출 실패는 hard blocker가 아니다. FE는 사용자에게 계속 진행 여부를 묻고, 계속 진행하면 `POST /analysis-runs`에 `documentId` 없이 진행할 수 있다.

## GitHub URL 정규화

지원:

- `https://github.com/owner/repo`
- `http://github.com/owner/repo`
- `github.com/owner/repo`
- issue, PR, commit, blob, tree 하위 URL은 `owner/repo`까지 정규화한다.

정규화:

- trailing slash 제거
- query/hash 제거
- `.git` 제거
- `owner/repo` full_name 생성

제외:

- gist
- GitLab
- Bitbucket
- URL 없이 `owner/repo` 텍스트만 있는 패턴

unmatched URL을 사용자에게 어떻게 보여줄지는 `PENDING_FE`.
