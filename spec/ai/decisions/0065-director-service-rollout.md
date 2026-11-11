# 0065 Director 개선 정책의 서비스 기본 연결과 단일 통합 게시

상태: Accepted for implementation and publication, 2026-11-11.

## 맥락

[0052](0052-director-problem-oriented-evaluation.md)부터
[0064](0064-director-evaluation-key-semantic-fit.md)까지는 로컬 개발·평가에서
정책을 비교하기 위한 결정이다. 사용자는 현재 개선 내용을 서비스에 반영하고,
문제·해결 과정·결과를 레퍼런스 이슈로 정리한 뒤 하나의 PR로 게시하도록 요청했다.
이는 과거 평가 기록의 기본값 유지 결정을 이후 서비스 연결 범위에서 대체한다.

평가·계측에는 범용 레포 분석 작업의 미게시 공통 기반 12파일을 채택했다.
이를 제외하면 평가 runner와 실제 호출·Langfuse 계측을 함께 검증할 수 없다.
사용자는 이 12파일을 포함하는 방안을 명시적으로 선택했다.

## 결정

- 서비스 catalog의 Director base version은 `director_v17`, 본문은
  `director-runtime-v17-semantic-fit.md`로 연결한다. 답변 분석은
  `answer_analysis_v7`와 `answer-analysis-runtime-v7-claim-contribution-scope.md`를
  연결한다. 실험의 `@semantic-fit`·`@claim-contribution-scope` 식별자를 base version에
  넣지 않는다. `--deployment`는 검증된 식별자를 붙이는 단일 suffix로 유지한다.
- 최신 develop의 다른 활성 task·리포트와 시간 제한 처리를 보존한다.
  카탈로그 전체를 읽고 소비자의 버전 지원을 검사한 뒤 하나의 트랜잭션으로 등록한다.
  모델과 호출 제한은 실제 설정에서 읽는다. 이번 게시를 위해 사용자의 추론 강도·
  출력 상한·연결 모델·시간 예산을 임의 변경하지 않는다.
- 새 질문의 요청 기반 계약·독립 Review, T3 원문 구절과 기여 범위, 원문 결합 복구를
  함께 게시한다. 구버전 질문·분석을 읽는 decoder와 기존 실패 원본은 보존한다.
  새 데이터가 저장된 뒤 구버전 실행 이미지로 되돌리는 방법을 기본 롤백으로 삼지 않는다.
- 자동 복구는 기존 슬롯 1개와 실패 당시 입력·정책 결합 조건 안에서만 수행한다.
  진행 중인 면접의 정책을 고정한 것처럼 설명하지 않는다. 실패 기록과 활성 version·본문이
  다르면 안전 검사를 약화하지 않고 해당 복구를 거절한다.
- 일반 게시 지침의 명세·구현 분리 대신 사용자의 이번 요청에 한해 단일 통합 PR로 게시한다.
  원본 작업 트리·원문·실험 기록을 보존하고, 최신 develop의 별도 통합 환경에서 검증한 뒤
  별도 게시 브랜치로 옮긴다. 다른 미병합 PR의 자동 병합이나 다른 작업의 게시 권한으로
  이 예외를 확대하지 않는다.

## 채택한 공통 기반의 출처

공통 12파일은 아래와 같다. 전체를 이번 Director 작업의 신규 저작물로 설명하지 않는다.

| 범위 | 파일 |
| --- | --- |
| 공통 평가 실행 | `ai/evals/eval_runner.py`, `recorded_grader.py`, `repository_sources.py` |
| 평가 검증 | `ai/tests/test_recorded_grader.py` |
| 실제 호출·계측 | `backend/app/integrations/execution_ledger.py`, `execution_langfuse.py`, `llm/client.py` |
| 집계 명령 | `backend/scripts/execution_metrics.py` |
| 계측 검증 | `backend/tests/integrations/test_llm_execution_ledger.py`, `backend/tests/test_execution_ledger.py`, `test_execution_langfuse.py`, `test_execution_metrics_cli.py` |

개발 원본에서 채택 상태 7파일은 유지했고 5파일에는 Director 후속 변경이 있다.
서비스 연결 검토에서는 `execution_ledger.py`에도 선택 관측의 I/O 오류 격리를 추가했다.
최초 원문을 정확히
복원하지 못한 `eval_runner.py`·`execution_langfuse.py`·`test_execution_langfuse.py`는
추정한 최초 버전을 만들어 차이를 입증하지 않는다. 확인 가능한 채택 상태와 이후 변경의
해시·범위를 보존하며, 실제 게시 범위는 develop 대비 diff로 확인한다.

## 배포·전환·롤백 경계

코드와 catalog 연결만으로 기존 DB의 활성 프롬프트가 바뀌지는 않는다.
배포는 기존 API·worker 중지, 마이그레이션, 새 소비자로 catalog 등록,
소비자 시작 순서를 따른다. 이미 진행·실패 중인 면접의 복구 version 결합을 확인하고,
기존 정책이 필요한 면접을 종료·유지할 전환 범위를 배포 전에 판단한다.

`--deployment`를 쓰면 기존 불변 버전을 보존한 새 배포 버전을 등록한다. 같은
version의 본문을 덮어써 불변성 검사를 우회하지 않는다. 새 v7 분석이 생긴 뒤에는
신규 decoder를 유지하면서 보존한 이전 PromptSpec을 재활성화하는 방향으로 롤백한다.
모델·다른 task의 활성 정책까지 함께 바뀌는지 실제 manifest를 확인한다.

격리 PostgreSQL·Redis와 실제 Luna의 서비스 함수 검증은 운영 DB 변경·배포와 다르다.
OAuth·브라우저·WS·음성·모든 레포의 전체 품질을 대신 증명하지 않는다.
사람 검수·전문가의 측정 타당성 승인과 Codex 원문 대조·자동 검증을 구분한다.

선택 관측의 장부 초기화·start·finish에 생긴 `OSError`·SQLite `OperationalError`는
실제 면접 결과를 중단시키지 않는다. 고정 이벤트와 예외 타입만 남기며 미완료 기록을
성공·사용량 0으로 바꾸지 않는다. 평가 실행은 기본 strict로 유지한다. validator·
프로그래밍 오류·업무 실패·취소는 숨기지 않고 원래 경계를 따른다.

## 근거와 영향

별도 자율 Agent·embedding·RAG·새 실행 프레임워크는 이번에 추가하지 않는다.
재현한 오류가 질문 계약·원문 범위·검토·답변 해석·복구에 있으므로 기존 호출·저장
경로를 보완하는 방법을 선택했다. 새로운 검색 계층이 필요하면 같은 오류·지연·비용
기준으로 별도 비교한다. 최신 개발 사례의 성과를 미사용 holdout의 정확도로 해석하지 않는다.

영향은 AI 내부 계약·BE 소비자·평가 도구·운영 활성화 순서에 있다. 공개 REST/WS payload와
DB schema를 새로 정의하지 않는다. 실제 검증 결과와 남은 개선은 한 곳인
[구현 기록](../implementation.md)에 남긴다. 문제·해결 과정·결과의 설명은
[레퍼런스 이슈 #269](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/269)를 따른다.
