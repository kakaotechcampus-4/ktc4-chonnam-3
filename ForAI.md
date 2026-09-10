# AI 검토 필요 사항

작성일: 2026-09-10

이 문서는 백엔드가 임의로 확정하지 않고 AI 리드 또는 AI 파트 검토가 필요한 항목을 모은다. 전체 변경/확정 기록은 `report.md`를 본다.

## 1. pgvector / embedding 검색 도입 여부

상태: `PENDING_AI`

결정 필요:

```text
Sprint 1 migration에 pgvector extension을 포함할지,
아니면 Sprint 1은 relational/keyword/LLM structured output 기반으로 두고
Sprint 2에서 vector 검색을 도입할지
```

현재 백엔드 문서의 가정:

- `pgvector`는 아직 migration FIX 대상이 아니다.
- evidence 검색은 Sprint 1에서 README, metadata, languages, commit metadata, L2 `notable_areas[].path` 주변 파일을 우선 사용한다.
- vector 검색이 없어도 Sprint 1의 repo 추천, 면접 질문 생성, answer-vs-code conflict 기록은 동작해야 한다.

AI가 확인할 지점:

- repo 추천, Evidence Retriever, report/profile summary 중 embedding이 실제로 필요한 구간.
- 사용할 embedding model, vector dimension, chunk 단위, 재색인 기준.
- vector를 Postgres `pgvector`에 저장할지, 별도 vector store를 둘지.
- Sprint 1에 extension만 미리 넣는 것이 migration 리스크보다 이득이 큰지.

## 2. Prompt output schema 생성 가능성

상태: AI 검토 필요

Sprint 1 백엔드 FIX 가정:

- 모든 LLM 작업은 `5.5 Luna`로 고정한다.
- prompt version은 작업별로 둔다.
- 대상 version: `repo_shallow_v1`, `repo_deep_v1`, `jd_extract_v1`, `answer_analysis_v1`, `director_v1`, `report_v1`, `profile_summary_v1`.
- LLM JSON parsing 실패는 1회 재시도 후 실패 처리하고 raw output을 저장한다.

AI가 확인할 지점:

- `5.5 Luna`가 각 task의 JSON schema를 안정적으로 생성할 수 있는지.
- 특히 `repo_deep_v1`의 `notable_areas` 필수 생성, `answer_analysis_v1`의 검증 가능 claim 분리, `director_v1`의 persona/turn 선택이 현재 schema로 충분한지.
- broken JSON을 repair prompt로 다시 고칠지 여부. 현재 Sprint 1 문서는 repair 없이 1회 재시도 후 실패로 고정했다.

## 3. Domain lead question frame

상태: AI 검토 필요

확정된 방향:

- `domain_lead`는 JD 요구사항 질문자가 아니다.
- 산업/서비스 도메인 관점 질문을 한다.
- 도메인 카테고리는 `finance`, `game`, `travel`, `shopping`, `medical`, `mobility`, `etc`.
- Sprint 1에서는 도메인별 question frame 3개씩 seed하고, 세부 질문은 prompt에서 생성한다.

AI가 확인할 지점:

- 각 도메인별 seed frame이 개인정보 처리, 관련 법/규제 인식, 유사 서비스 경험, 안정성/운영/UX 맥락을 충분히 커버하는지.
- `etc` 도메인의 fallback frame이 너무 일반적인 질문으로 흐르지 않는지.
- `domain_lead` 질문이 기술 질문과 중복되지 않도록 prompt guard가 필요한지.

## 4. Evidence Retriever 확장 여부

상태: AI 검토 필요

Sprint 1 백엔드 FIX 가정:

- 모든 질문에 사전 evidence를 강제하지 않는다.
- `tech_lead` 질문은 가능한 한 `question_basis` evidence를 붙인다.
- `domain_lead`, `hr_manager` 질문은 evidence 없이도 가능하다.
- 답변 분석 중 검증 가능한 주장이 나오면 후속 검색으로 `evaluation_basis` evidence를 붙인다.
- Sprint 1 검색 범위는 README, metadata, languages, commit metadata, L2 notable area 주변 파일이다.

AI가 확인할 지점:

- answer-vs-code conflict를 잡기에 Sprint 1 evidence 범위가 충분한지.
- full tree/global code search가 Sprint 1에 꼭 필요한지, 아니면 Sprint 2로 두어도 되는지.
- evidence가 부족한 답변을 `unverified`로 둘 기준과 추가 조회를 시도할 기준.

## 5. Report score와 AI prompt의 관계

상태: `PENDING_TEAM`, AI 단독 결정 아님

현재 보류 이유:

- 점수 산정 근거와 저장 스케일은 팀원이 자료를 보충한 뒤 확정하기로 했다.
- API에는 `totalScore`, `scores[].score` shape가 있지만, 실제 공식은 아직 고정하지 않는다.

AI가 유의할 점:

- report prompt에서 임의의 0~100 공식이나 1~5 루브릭을 고정하지 않는다.
- Sprint 1 구현은 response shape, feedback, evidence 연결, disagreement 기록을 우선한다.
- 팀 기준이 확정되면 `score_criteria` seed와 `report_v1` prompt를 함께 수정한다.

## 6. Sprint 2 모델/검색 전략

상태: Sprint 2 재검토

확정된 Sprint 1 방향:

- AI 리드 의견에 따라 Sprint 1은 `5.5 Luna` 단일 모델로 비용, token, latency, output 품질을 측정한다.
- 실제 사용 모델 문자열, prompt version, token, latency는 가능한 범위에서 저장한다.

AI가 Sprint 2 전에 확인할 지점:

- task별 모델 분리 필요 여부.
- voice/STT/TTS 추가 시 realtime 모델 또는 별도 음성 provider 사용 여부.
- token 비용이 큰 task가 `repo_deep`, `answer_analysis`, `report` 중 어디인지.
- embedding/vector 검색을 도입할 경우 기존 prompt 구조를 얼마나 줄일 수 있는지.
