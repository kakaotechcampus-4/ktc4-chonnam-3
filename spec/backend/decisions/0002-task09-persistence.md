# 0002 Task 9 공고 버전 보존과 문서 Preview 저장 경계

- 상태: Accepted — Task 9 API·저장 Draft의 내부 설계; 구현·연결 완료 상태가 아님
- 날짜: 2026-09-28
- 근거: 사용자가 선행 PR을 병합하지 않고 develop 기준으로 Task 9 API·공고 저장만 분리한 신규 Draft를 승인함
- 관련 PR: 선행 [#44](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/44), [#57](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/57); 이전 작업 [#78](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/78)은 닫힌 상태로 보존
- 검토: 설계·검증 범위를 아래와 같이 분리하며 실제 구현·실행 결과는 [구현 기록](../implementation.md)에 둔다.

## 맥락

기존 정책은 20MiB 포트폴리오, 7일 공고 재사용, 변경 공고의 새 자료 ID와 과거 참조 보존을 요구한다.
초기 DB의 URL UNIQUE는 같은 URL의 새 버전 저장을 막는다. Preview 공개 계약은 file 하나를 받아
documentId와 extractStatus만 반환하며, 공고 URL은 받지 않는다.

## 결정

1. 공고 이력은 기존 job_postings와 jd_requirements의 새 행으로 보존한다. 초기 migration은 수정하지
   않고 0002에서 URL UNIQUE를 일반 조회 인덱스로 바꾼다. 중복 URL이 존재하면 downgrade를 거절한다.
2. URL별 최신 생성 성공본의 fetched_at으로 7일 이내 여부를 판정한다. 캐시 조회는 시각을 늘리지 않는다.
   재수집 내용이 같으면 같은 ID를 유지하고 fetched_at만 갱신한다. 내용이 바뀌면 새 ID들을 원자 저장한다.
3. HTTP 이후 짧은 PostgreSQL URL advisory transaction lock 안에서 현재 자료를 다시 확인한다.
   중복 HTTP는 허용하되 중복 자료 확정은 막는다. 수집 실패가 기존 성공 자료를 덮어쓰지 않는다.
4. raw_payload는 PostingContent의 원문 그룹·메타데이터 스냅샷이다. 실제 HTTP JSON 전체라는 뜻이 아니다.
   fetch_url 표기만 제외한 내용과 저장된 요구사항을 비교한다. 요구사항 순서와 원문 그룹을 보존하며
   source_field는 기존 category와의 대응으로 복원한다. 해시 컬럼이나 별도 이력 테이블은 추가하지 않는다.
5. Preview는 공개 API와 선행 추출기의 호출 계약을 유지한다. JD를 받지 않으므로 JD 수집 없이
   추출된 본문의 GitHub URL 주변·프로젝트 헤딩을 우선 보관한다. 본문의 URL 목록을 먼저 확보하고
   텍스트를 축약한다. 본문에 없는 PDF/DOCX 링크 대상 추출과 파서 보완은 별도 후속 범위다.
6. 기존 extracted_text는 최종 보관 텍스트, extracted_github_urls는 축약 전 확보한 저장소 목록이다.
   초기 구현 상한 DOCUMENTS_MAX_TEXT_CHARS=50000은 조정 가능한 운영 설정이며 기존 합의 수치가 아니다.
   별도 원문/요약 컬럼과 바이너리 보관은 추가하지 않는다. 축약·일부 추출은 partial로 표시한다.
7. 지원 파일의 추출 실패도 실제 문서 행을 저장하고 200/failed를 반환한다. 형식·크기 거절은
   415/413, 인증 실패는 401이다. DB 장애·예상하지 못한 구현 오류를 추출 실패로 숨기지 않는다.

## 이유와 영향

기존 테이블·응답과 과거 자료의 의미를 유지한다. URL 락을 잡은 채 네트워크를 호출하는 대안보다
DB 점유가 짧고, 별도 Redis 자료 락·이력 테이블보다 구성 요소가 적다. Task 11은 저장된 공고 ID를
run에 고정하며, URL로 최신 공고를 다시 골라 과거 면접에 끼우지 않는다.

공개 API 필드·enum은 바꾸지 않는다. 포트폴리오 네 형식과 자소서 제외에 관한 기존 FE 수정 보류도
유지한다. 브라우저 화면 전체 연결 완료는 해당 후속 수정 및 task 11과 구분한다.

Draft는 선행 PR의 인증, 추출기, 관련 의존성·기존 테스트를 가져오지 않는다. 필요한 인증·추출
인터페이스가 준비된 환경에서 API·저장 동작을 검증하며, 선행 구현 없이 실행 가능한 전체 Task 9로
취급하지 않는다. 선행 구현을 일시 결합한 로컬 검사는 develop 단독 실행 결과와 구분한다.

## 대체 관계

[공통 0002](../../shared/decisions/0002-local-policy-baseline.md), [AI 0014](../../ai/decisions/0014-minimal-change-revision.md)의 정책을 유지하고 내부 저장·동시성 구현을 구체화한다.
과거 문서의 JD 키워드 Preview 축약 설명은 file-only 공개 계약에 맞는 위 방식으로 좁힌다.
PR #45의 별도 ADR 0001과 식별자가 겹치지 않도록 이 신규 기록은 0002를 사용한다.
