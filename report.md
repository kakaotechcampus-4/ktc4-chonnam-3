# 기획 변경·확정 Report

작성일: 2026-09-10

## 1. 면접 입력 방식

### 의견 충돌 지점/의논이 안된 부분

기존 FE/API 문서에는 오디오 chunk, STT transcript, TTS 응답이 Sprint 1 범위처럼 섞여 있었다.

### 확정한 내용

Sprint 1은 텍스트-only 면접으로 한다. Sprint 2에서 음성 연결, STT, TTS를 추가한다.

### 이유

DB가 `answer_mode='text'` 중심이고, Sprint 1은 핵심 면접 흐름 검증이 우선이다. 음성은 브라우저/외부 API/포맷 의존성이 커서 Sprint 2로 분리한다.

## 2. WS 식별자

### 의견 충돌 지점/의논이 안된 부분

`interviewId` 하나로 WS까지 붙일지, 별도 `sessionId`를 유지할지 FE 라우팅과 상태 복구 정책이 필요하다.

### 확정한 내용

`PENDING_FE`로 보류한다. 관련 내용은 루트 `ForFE.md`에도 정리했다.

### 이유

FE 라우팅을 지금 변경 판단할 수 없고, 새로고침/재연결/중복 접속 UX와 같이 결정해야 한다.

## 3. 텍스트 WS 메시지

### 의견 충돌 지점/의논이 안된 부분

기존 메시지는 `answerStart` -> audio chunk -> `answerEnd` 흐름이었다.

### 확정한 내용

Sprint 1 client message는 `{ "type": "answer", "text": "..." }`로 단순화한다. server message는 `answerReceived`, `thinking`, `evidenceCheck`, `question`, `interviewEnd`, `error`를 사용한다. 텍스트 WS에서 `questionEnd`를 유지할지는 `PENDING_FE`.

### 이유

텍스트 답변은 단일 payload로 완결된다. 음성/TTS 스트리밍용 이벤트는 Sprint 2에서 다시 결정하는 편이 안전하다.

## 4. Analysis partial 상태

### 의견 충돌 지점/의논이 안된 부분

DB에는 `partial`이 필요하지만 FE `RunStatus`는 `running`, `completed`, `failed` 3값이다.

### 확정한 내용

DB `partial`은 유지하되 FE에는 `failed`로 매핑한다. `partial`이어도 `/analysis-runs/{runId}/result`는 조회 가능하게 둔다.

### 이유

일부 repo 결과는 디버깅과 후속 확장에 필요하지만, 사용자가 보는 기본 흐름은 실패 화면으로 보내는 게 현재 UX에 맞다.

## 5. Repo analysis cache UNIQUE

### 의견 충돌 지점/의논이 안된 부분

`repo_analyses` UNIQUE에 `model`을 넣을지 여부가 미결이었다.

### 확정한 내용

UNIQUE에는 `model`을 넣지 않는다. `model` 컬럼은 저장만 한다. UNIQUE는 `(repository_id, analysis_level, head_sha, prompt_version)` 기준이다.

### 이유

Sprint 1은 모델 A/B가 아니라 전체 기능 완주가 목표다. 모델 비교는 Sprint 2 이후 별도 정책으로 다룬다.

## 6. 공고 필수 여부와 지원 사이트

### 의견 충돌 지점/의논이 안된 부분

기존 문서에는 unsupported site에서 공고 없이 진행하는 흐름이 있었다.

### 확정한 내용

면접은 공고 필수다. Sprint 1은 Wanted만 지원하고, 다른 사이트는 `unsupported_site`로 차단한다. 공고 없는 면접은 범위 밖이다.

### 이유

회의 결과 공고는 무조건 입력하기로 했고, `job_posting_id NOT NULL`, `company_job_fit`, `coverage` 구조와도 일치한다.

## 7. Report 점수

### 의견 충돌 지점/의논이 안된 부분

API는 0~100 점수처럼 보이고, 내부 루브릭은 1~5 기준 흔적이 있다.

### 확정한 내용

점수 산정 근거와 저장 스케일은 `PENDING_TEAM`으로 보류한다.

### 이유

팀원이 관련 자료를 보충한 뒤 확정하기로 했다. 임의로 0~100/1~5 변환식을 고정하면 나중에 평가 기준이 흔들린다.

## 8. Document claims

### 의견 충돌 지점/의논이 안된 부분

기존 backend docs는 `document_claims`를 Sprint 1에 포함한다고 되어 있었고, 이후 브레인스토밍에서는 Sprint 1에서 아예 만들지 않는 방향도 논의했다.

### 확정한 내용

`document_claims`는 Sprint 1 migration에 만들되 row 생성/claim 추출은 하지 않는다. 자소서/포트폴리오 claim 추출은 Sprint 2에서 함께 구현한다.

### 이유

회의 결과 Sprint 1에서는 문서 claim을 받지 않고, 포트폴리오는 GitHub URL 추천 신호 정도로만 쓰기로 했다. 다만 Sprint 2 확장 구조를 유지하기 위해 테이블은 미리 만든다.

## 9. Evidence conflicts

### 의견 충돌 지점/의논이 안된 부분

`evidence_conflicts`가 document claims와만 연결되는지, 사용자 답변과 repo evidence 충돌에도 쓸 수 있는지 확인이 필요했다.

### 확정한 내용

Sprint 1에 `evidence_conflicts`를 만들고 `answer_vs_code` 용도로 사용한다. `claim_id`는 nullable UUID지만 FK는 Sprint 2에 추가한다.

### 이유

현재 설계상 `claim_id`는 nullable이고 `source='answer_vs_code'`가 가능하다. 사용자의 답변과 GitHub 근거가 어긋날 때 즉시 꼬리질문으로 이어지는 핵심 기능에 필요하다.

## 10. Redis 사용 범위

### 의견 충돌 지점/의논이 안된 부분

정밀분석 자료(JD, notable areas 등)를 Redis에 담아두는 것이 적절한지 논의했다.

### 확정한 내용

원본은 PostgreSQL에 저장하고, Redis에는 면접 진행용 context snapshot만 TTL 2시간으로 둔다.

### 이유

면접 중 빠르게 읽는 작업 기억은 Redis에 적합하지만, 유실되면 안 되는 분석 결과와 기록은 Postgres가 원본이어야 한다.

## 11. Report 생성

### 의견 충돌 지점/의논이 안된 부분

면접 종료 직후 자동 생성할지, 리포트 화면 진입 시 lazy generation할지 논의했다.

### 확정한 내용

Lazy generation으로 한다. `GET /interviews/{id}/report`에서 없으면 `report_generate` job을 enqueue하고 202를 반환한다.

### 이유

면접 종료 직후 바로 리포트 화면으로 이동하므로 자동 enqueue가 만드는 체감 속도 차이가 작다. lazy 방식이 race condition과 실패 경계를 줄인다.

## 12. Profile summary

### 의견 충돌 지점/의논이 안된 부분

`user_profile_summaries`를 Sprint 1에 만들지, Sprint 2에 추가할지 논의했다.

### 확정한 내용

Sprint 1 DB에 포함한다. report 생성 성공 후 `profile_summary` job을 후속 enqueue한다. 집계 기준은 완료 면접에 사용된 repo다.

### 이유

FE 홈 화면 UI가 고정되어 있고, Sprint 2에서 누적 완료 repo 기반 인사이트를 강화해야 한다.

## 13. Event tracking

### 의견 충돌 지점/의논이 안된 부분

events를 Sprint 1부터 넣을지 범위가 불명확했다.

### 확정한 내용

Sprint 1부터 최소 10개 이벤트를 고정한다. `interview_abandoned`는 `PENDING_FE`.

### 이유

완주율, 추천 품질, evidence 사용률 같은 핵심 지표를 초기에 관측해야 한다. 이탈 판정은 FE 정책과 연결되어 보류한다.

## 14. GitHub repo 범위

### 의견 충돌 지점/의논이 안된 부분

private repo를 Sprint 2에서 지원할지 논의했다.

### 확정한 내용

public repo만 지원한다. private repo는 Sprint 2에서도 고려하지 않고 필드만 둔다.

### 이유

권한 부담과 토큰 scope가 커진다. 현재 서비스 핵심은 public GitHub repo 기반 면접이다.

## 15. Repo filter

### 의견 충돌 지점/의논이 안된 부분

`size_kb > 50`을 절대 기준으로 고정할지 논의했다.

### 확정한 내용

public, non-fork, non-archived, primary language 있음은 고정한다. `size_kb` threshold는 기본값만 두고 조정 가능하게 한다.

### 이유

작은 repo 제외는 필요하지만, 프로젝트 성격에 따라 적정 threshold가 달라질 수 있다.

## 16. Analysis StepKey

### 의견 충돌 지점/의논이 안된 부분

`doc_extract`가 claim 추출처럼 보일 수 있었다.

### 확정한 내용

7개 step을 유지한다. Sprint 1의 `doc_extract`는 문서에서 GitHub URL만 반영하고 claim 추출은 하지 않는다.

### 이유

FE/BE/AI 진행 단계는 7개로 맞추되, Sprint 1 문서 처리 범위를 명확히 제한하기 위함이다.

## 17. Candidate 더 보기

### 의견 충돌 지점/의논이 안된 부분

전체 repo를 한 번에 보여줄지, 10개 단위로 보여줄지 논의했다.

### 확정한 내용

전체 repo를 한 번에 보여주지 않는다. 전체 public repo에 lightweight ranking을 만들고, batch/page 단위로 L0-b/L1 분석 후 10개씩 보여준다.

### 이유

사용자가 전체 repo에서 찾는 부담을 줄이고, 서비스가 연관성을 따져 추천한다는 UX를 유지하기 위해서다.

## 18. Candidate ranking 저장소

### 의견 충돌 지점/의논이 안된 부분

영구 데이터가 아니라 Redis에 둘 수 있는지 논의했다.

### 확정한 내용

`analysis_repo_candidates`와 `analysis_repo_candidate_pages`를 Postgres에 둔다. Redis는 page cache 정도로만 쓸 수 있다.

### 이유

Ranking은 run 결과 화면의 재현성, 새로고침, 디버깅에 필요하다. Redis TTL 만료로 순서가 사라지면 UX와 검증이 흔들린다.

## 19. Candidate 첫 batch 구성

### 의견 충돌 지점/의논이 안된 부분

L0-a lightweight ranking만으로 첫 page에 사용자가 원하는 repo가 올라올지 불확실했다.

### 확정한 내용

첫 batch 10개는 혼합 전략으로 구성한다. portfolio mentioned 최대 3개, base rank top 최대 5개, JD signal 최대 2개, high contribution 최대 2개를 중복 제거한다.

### 이유

단순 최근순/가벼운 ranking만 쓰면 오래됐지만 중요한 repo가 빠질 수 있다.

## 20. Candidate page 분석 방식

### 의견 충돌 지점/의논이 안된 부분

추가 page를 API 요청 안에서 바로 분석할지, queue로 넘길지 논의했다.

### 확정한 내용

ARQ job으로 넘긴다. 미분석 page 요청 시 `202 analyzing`을 반환하고 완료 후 `200`을 반환한다.

### 이유

L0-b와 L1은 수 초~수십 초 걸릴 수 있으므로 API request 안에서 오래 처리하면 timeout/UX 문제가 생긴다.

## 21. 면접 repo 선택 조건

### 의견 충돌 지점/의논이 안된 부분

L1 실패 repo가 선택될 가능성을 어떻게 막을지 확인했다.

### 확정한 내용

`POST /interviews`는 current run, public, accessible, candidate eligible, L1 succeeded repo만 허용한다. 최소 1개, 최대 5개.

### 이유

L1 실패 repo가 추천/선택 가능 카드가 되는 것은 버그다. API에서도 방어해야 stale UI와 직접 호출을 막을 수 있다.

## 22. Run당 면접 수

### 의견 충돌 지점/의논이 안된 부분

같은 run에서 여러 면접 세션을 만들 수 있게 할지 논의했다.

### 확정한 내용

Sprint 1에서는 run당 활성 면접 1개만 허용한다. 재시도는 `/interviews/{id}/retry`를 사용한다.

### 이유

레포 조합을 바꿔 새 면접을 만드는 기능은 복잡도를 키운다. Sprint 1은 핵심 흐름 안정화가 우선이다.

## 23. Interview prep

### 의견 충돌 지점/의논이 안된 부분

면접 준비를 `POST /interviews` 직후 시작할지, WS 연결 시 시작할지 논의했다.

### 확정한 내용

`POST /interviews` 성공 직후 `interview_prep` job을 enqueue한다.

### 이유

사용자가 준비 화면으로 이동하는 동안 L2 deep analysis와 context snapshot 생성을 시작할 수 있다.

## 24. Prep 실패 상태

### 의견 충돌 지점/의논이 안된 부분

준비 실패를 `abandoned`와 섞을지 논의했다.

### 확정한 내용

`interview_sessions.status='preparing_failed'`를 추가한다. FE 매핑은 `PENDING_FE`.

### 이유

`abandoned`는 사용자 이탈이고, 준비 실패는 시스템/외부 의존 실패다. 원인과 UX가 다르다.

## 25. 첫 질문

### 의견 충돌 지점/의논이 안된 부분

첫 질문을 기술 리드가 할지 HR이 할지 논의했다.

### 확정한 내용

첫 질문은 `hr_manager`가 한다. 긴장 완화 목적이며 evidence 없이 허용한다.

### 이유

회의 결과 사용자 완화 후 Director가 자연스럽게 진행하는 방식으로 정했다.

## 26. Turn 배분

### 의견 충돌 지점/의논이 안된 부분

`domain_lead`와 `hr_manager`의 3턴 배분을 고정할지 논의했다.

### 확정한 내용

총 9턴. `tech_lead` 목표 6턴, 최소 5턴. `domain_lead + hr_manager` 합산 최소 3턴. 두 persona의 배분은 Director 판단.

### 이유

기능적으로 persona 선택 흐름을 보여주는 것이 중요하고, 고정 규칙보다 질문 맥락에 따른 선택이 낫다.

## 27. 기술 질문 범위

### 의견 충돌 지점/의논이 안된 부분

선택된 repo 전체를 균등하게 물을지, 주요 repo에 집중할지 논의했다.

### 확정한 내용

primary repo 1~2개 중심으로 꼬리질문 품질을 우선한다.

### 이유

서비스 핵심은 균등 커버리지가 아니라 GitHub 근거 기반 꼬리질문 품질이다.

## 28. Domain lead 역할

### 의견 충돌 지점/의논이 안된 부분

`domain_lead`를 JD 요구사항 질문자로 오해할 수 있었다.

### 확정한 내용

`domain_lead`는 산업/서비스 도메인 관점 질문을 한다. 도메인은 `finance`, `game`, `travel`, `shopping`, `medical`, `mobility`, `etc`.

### 이유

회의 결과 도메인 세부지식보다 개인정보 처리, 규제, 서비스 사용 경험, 신뢰성 같은 고정 질문 프레임을 세부 프롬프팅하는 방향으로 정했다.

## 29. Evidence 보강

### 의견 충돌 지점/의논이 안된 부분

질문 생성 시 evidence가 없는 persona 질문을 허용할지 논의했다.

### 확정한 내용

질문 근거와 평가 근거를 분리한다. evidence가 부족한 답변은 T3에서 Evidence Retriever가 후속 검색해 `evaluation_basis`를 붙인다.

### 이유

모든 질문에 사전 evidence를 강제하면 domain/hr 질문이 과하게 제한된다. 반면 평가/피드백에는 근거가 필요하다.

## 30. Evidence Retriever 범위

### 의견 충돌 지점/의논이 안된 부분

전체 repo 검색을 Sprint 1에 넣을지 논의했다.

### 확정한 내용

Sprint 1은 README, metadata, languages, commit metadata, L2 `notable_areas[].path` 주변 파일만 조회한다.

### 이유

전체 tree scan/keyword search는 비용과 속도 부담이 크다. Sprint 1은 L2가 제공한 path를 시작점으로 좁힌다.

## 31. Notable areas

### 의견 충돌 지점/의논이 안된 부분

L2 deep analysis에서 `notable_areas`를 필수로 둘지 논의했다.

### 확정한 내용

primary repo마다 `notable_areas` 최소 1개, 최대 5개를 필수로 둔다. path는 파일/디렉터리 모두 허용한다.

### 이유

Evidence Retriever가 실제 근거를 찾는 시작점이 필요하다. path가 없으면 deep analysis 품질을 partial로 봐야 한다.

## 32. 문서 preview 저장

### 의견 충돌 지점/의논이 안된 부분

문서 원문을 저장하지 않고 URL만 뽑을지, 텍스트 원문도 저장할지 논의했다.

### 확정한 내용

파일 바이너리는 저장하지 않고 텍스트 원문, GitHub URL, 메타데이터를 저장한다. `document_claims` 테이블은 만들지만 claim row 생성은 Sprint 2.

### 이유

2차에서 같은 문서를 다시 요구하지 않아도 되고, DB 구조는 크게 바뀌지 않는다. 바이너리 저장은 개인정보/스토리지 부담이 커서 제외한다.

## 33. 문서 길이 초과

### 의견 충돌 지점/의논이 안된 부분

긴 문서를 LLM 요약할지 논의했다.

### 확정한 내용

LLM 요약을 쓰지 않는다. JD keyword, GitHub URL 주변 문장, 헤딩/프로젝트 섹션 중심으로 축약한다.

### 이유

Sprint 1에서 문서는 보조 신호다. LLM 요약까지 넣으면 비용과 실패 경계가 늘어난다.

## 34. 문서 추출 실패

### 의견 충돌 지점/의논이 안된 부분

문서 추출 실패 시 분석 run을 실패시킬지 논의했다.

### 확정한 내용

`POST /documents/preview`를 별도 API로 두고, 실패/partial이면 FE가 사용자에게 계속 진행 여부를 묻는다. 계속 진행하면 `documentId` 없이 `POST /analysis-runs`를 호출한다.

### 이유

문서는 Sprint 1에서 보조 신호이고, 공고 + GitHub public repo만으로도 추천은 가능하다.

## 35. 문서 지원 형식

### 의견 충돌 지점/의논이 안된 부분

HWP, 이미지, PPT까지 Sprint 1에 넣을지 논의했다.

### 확정한 내용

Sprint 1은 PDF, DOCX, TXT, MD만 지원한다. 파일 최대 크기는 10MB.

### 이유

이 4가지는 구현/테스트가 명확하다. HWP/OCR/PPT는 환경과 추출 품질 의존성이 크다.

## 36. GitHub URL 추출

### 의견 충돌 지점/의논이 안된 부분

GitHub 하위 URL, gist, owner/repo 텍스트 패턴을 어디까지 허용할지 논의했다.

### 확정한 내용

GitHub repo URL과 issue/PR/commit/blob/tree 하위 URL을 `owner/repo`로 정규화한다. gist, GitLab, Bitbucket, URL 없는 `owner/repo` 텍스트는 제외한다.

### 이유

오탐을 줄이면서 실제 포트폴리오 링크는 충분히 반영할 수 있다.

## 37. 인증

### 의견 충돌 지점/의논이 안된 부분

GitHub OAuth token과 DEVON 자체 JWT 역할이 섞여 있었다.

### 확정한 내용

GitHub token은 GitHub API용 외부 토큰이고 FE에 노출하지 않는다. BE가 암호화 저장한다. DEVON API 인증에는 BE가 만든 자체 JWT를 쓴다. JWT 전달 방식은 `PENDING_FE`.

### 이유

GitHub 권한 토큰과 서비스 인증 토큰을 분리해야 보안과 책임 경계가 명확하다.

## 38. LLM 모델

### 의견 충돌 지점/의논이 안된 부분

모델명을 환경값으로만 둘지, Sprint 1에서 고정할지 논의했다.

### 확정한 내용

Sprint 1은 모든 LLM 작업을 `5.5 Luna`로 고정한다. 실제 사용 모델명과 token/latency는 저장한다.

### 이유

AI 리드 의견에 따라 1차에서 같은 모델로 전체 흐름과 비용/품질을 측정한 뒤 2차에서 바꾼다.

## 39. Prompt version

### 의견 충돌 지점/의논이 안된 부분

전역 prompt version 하나를 쓸지 작업별로 나눌지 논의했다.

### 확정한 내용

작업별 prompt version을 둔다.

### 이유

프롬프트 변경 시 영향을 받는 캐시와 결과만 무효화할 수 있어야 한다.

## 40. LLM 실패 처리

### 의견 충돌 지점/의논이 안된 부분

JSON parsing 실패 fallback을 둘지 논의했다.

### 확정한 내용

자동 1회 재시도 후 실패 처리한다. 깨진 JSON은 복구해서 downstream에 넘기지 않는다.

### 이유

구조화 결과에 downstream이 의존하므로 임의 복구는 테스트와 디버깅을 어렵게 한다.

## 41. API 계약 원본

### 의견 충돌 지점/의논이 안된 부분

FE 문서, backend docs, spec/shared/contracts 중 어디를 원본으로 볼지 불명확했다.

### 확정한 내용

`spec/shared/contracts/openapi.yaml`을 API 계약 원본으로 승격한다.

### 이유

Claude 구현과 FE/BE 타입을 하나의 계약에 맞춰야 drift를 줄일 수 있다.

## 42. 문서 경계

### 의견 충돌 지점/의논이 안된 부분

`context`, `spec`, `backend/docs`, `backend/CLAUDE.md`의 역할이 섞일 수 있었다.

### 확정한 내용

`spec/backend`는 고정 설계, `spec/shared/contracts`는 공통 API 계약, `backend/docs`는 Claude 구현 체크리스트, `context`는 회의 기록으로 둔다.

### 이유

회의 기록을 바로 구현 기준으로 쓰면 충돌과 초안이 그대로 반영된다.

## 43. Migration 방식

### 의견 충돌 지점/의논이 안된 부분

Alembic autogenerate를 그대로 쓸 수 있는지 논의했다.

### 확정한 내용

초기 대형 migration은 수동 작성한다. autogenerate는 참고용이다.

### 이유

CHECK, UNIQUE, INDEX, JSONB, TEXT[], extension, Sprint 1/2 FK 경계를 autogenerate가 놓칠 수 있다.

## 44. pgvector

### 의견 충돌 지점/의논이 안된 부분

Sprint 1 migration에 pgvector extension을 넣을지 논의했다.

### 확정한 내용

`PENDING_AI`로 보류한다.

### 이유

AI 쪽에서 실제 embedding/vector 검색 필요 여부를 확인해야 한다.

## 45. 테스트 전략

### 의견 충돌 지점/의논이 안된 부분

외부 API/LLM을 실제 호출할지, mock할지 논의했다.

### 확정한 내용

GitHub, Wanted, LLM은 mock한다. 우리 로직은 PostgreSQL 기준으로 테스트한다.

### 이유

외부 의존성을 제거해야 안정적으로 실패 경계를 검증할 수 있고, JSONB/TEXT[]/partial index는 SQLite로 대체할 수 없다.

## 46. DB 테이블 필요성 재검토

### 의견 충돌 지점/의논이 안된 부분

브레인스토밍 과정에서 추가된 지식/평가/피드백 테이블이 Sprint 1 구현에 모두 필요한지 재검토가 필요했다.

### 확정한 내용

Sprint 1 생성/사용 테이블은 `score_criteria`, `prompt_versions`, `domain_question_frames`, `events`, `analysis_repo_candidates`, `analysis_repo_candidate_pages`를 유지한다. `document_claims`와 `report_disagreements`는 테이블만 만들고 Sprint 1에서는 row를 만들지 않는다.

`topic_taxonomy`, `interview_personas`, `probe_patterns`, `report_persona_feedbacks`, `feedback_signals`, `eval_cases`, `eval_runs`, `answer_analyses`, `director_decisions`는 Sprint 1 DB에서 제외한다. `auth_sessions`는 Sprint 2에서도 제외한다.

### 이유

테이블을 운영 데이터, 화면/API 재현성, 비동기 상태 추적에 필요한 것 위주로 줄였다. persona/topic/probe는 CHECK 값과 prompt 구조로 충분하고, 평가/범용 피드백 테이블은 핵심 사용자 플로우에 직접 필요하지 않다. 리포트 persona별 피드백은 스냅샷 성격이 강해 `interview_reports.feedback_json`이 더 단순하다.

## 47. github_accounts 토큰 필드

### 의견 충돌 지점/의논이 안된 부분

GitHub OAuth token과 DEVON 자체 JWT 역할이 분리되어 있는데, `github_accounts`에 만료/refresh token 필드를 둘 필요가 있는지 논의했다.

### 확정한 내용

일반 GitHub OAuth App long-lived access token을 전제로 한다. `github_accounts`에는 `access_token_encrypted`, `token_status`, `token_scope`만 둔다.

`token_type`, `token_expires_at`, `refresh_token_encrypted`, `refresh_token_expires_at`는 삭제한다. DEVON JWT는 `users.id`와 필요 시 `github_accounts.id` 같은 식별자만 사용하고, GitHub access token은 JWT payload에 넣지 않는다.

### 이유

현재 기획은 GitHub App user token이나 OAuth App expiring token을 쓰지 않는다. 따라서 refresh token을 받을 일이 없고, 자체 JWT 발급에도 GitHub token 필드가 필요하지 않다. 만료형 OAuth token 또는 GitHub App으로 전환하면 그때 별도 migration으로 추가하는 편이 더 단순하다.
