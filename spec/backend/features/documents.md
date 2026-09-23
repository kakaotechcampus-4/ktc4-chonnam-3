# 문서 Preview

상태: Sprint 1 FIX.

## 목적

문서는 Sprint 1에서 보조 신호다. `/documents/preview`는 포트폴리오 파일에서 GitHub URL을 추출하기 위한 경로로 사용한다. 자소서는 Sprint 1에서 preview POST 대상이 아니며, 자소서/포트폴리오 claim을 추출하지 않는다. `document_claims` 테이블은 Sprint 1 migration에 포함하지만 row는 생성하지 않는다.

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

- 포트폴리오 파일 최대 크기: 20MB(20,971,520 bytes). [현재 로컬 기준 채택 결정](../../shared/decisions/0002-local-policy-baseline.md)을 따른다.
- 파일 바이너리는 Sprint 1에서 저장하지 않는다.
- DB에는 filename, MIME type, size, extracted_text, extracted_github_urls, extract_status, truncation 여부만 저장한다.
- `document_claims` row 생성은 Sprint 2에서 자소서/포트폴리오 claim 추출을 함께 구현할 때 시작한다.

20MB 정책의 채택은 BE preview API의 크기 검사 구현 완료를 뜻하지 않는다. API 구현 시 같은 상한과 초과 거부를 검증한다.

## 상태

- `succeeded`: 텍스트/GitHub URL 추출 성공.
- `partial`: 일부 텍스트만 추출 또는 길이 초과 축약.
- `failed`: 추출 실패.

포트폴리오 추출 실패는 hard blocker가 아니다. FE는 사용자에게 계속 진행 여부를 묻고, 계속 진행하면 `POST /analysis-runs`에 `documentId` 없이 진행할 수 있다. `POST /analysis-runs.documentId`는 Sprint 1에서 portfolio preview document ID를 의미한다.

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

unmatched URL의 상세 목록은 노출하지 않고 [기존 포트폴리오 매칭 안내](../../frontend/features/analysis.md#포트폴리오-매칭-안내)에 따라 언급된 저장소 수와 매칭된 수만 안내한다. 실제 응답·화면 연결은 구현·검증할 작업이다.
