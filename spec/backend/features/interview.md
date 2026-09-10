# 면접

상태: Sprint 1 FIX.

## 생성

`POST /interviews`

- `runId`: 필수.
- `repositoryIds`: 1개 이상 5개 이하.
- 같은 `runId`에 활성 면접(`preparing`, `in_progress`)은 1개만 허용한다.
- 선택 repo는 current run, public, accessible, eligible, L1 succeeded여야 한다.
- 성공 직후 `interview_prep` ARQ job을 enqueue한다.

`/interviews/{id}/retry`

- 원본이 `completed` 또는 `abandoned`일 때만 허용한다.
- 원본의 run, 공고, repo 조합을 복사한다.
- 원본 repo가 삭제/접근불가/private 전환이면 `repository_unavailable`.

## 준비

`interview_prep` 수행:

- primary repo 1~2개 선정.
- primary repo L2 deep analysis 수행.
- `notable_areas` 생성/검증.
- 초기 `context_state` 생성.
- Redis interview context snapshot 생성.
- 첫 `hr_manager` 질문 생성.

Prepare step:

- `analyze_repo`: primary repo L2 deep analysis.
- `build_persona`: persona 후보/분포 초기화.
- `set_criteria`: JD, domain category, 평가 기준 context 구성.
- `compose_question`: 첫 질문 생성.

준비 실패:

- DB `interview_sessions.status='preparing_failed'`.
- `abandoned`와 구분한다.
- WS 진입은 차단한다.
- FE status 매핑은 `PENDING_FE`.

## WebSocket

Sprint 1은 양방향 텍스트다.

클라이언트 -> 서버:

```json
{ "type": "answer", "text": "답변 내용" }
```

서버 -> 클라이언트:

- `answerReceived`
- `thinking`
- `evidenceCheck`
- `question`
- `interviewEnd`
- `error`

`answerStart`, audio chunk, `answerEnd`, `transcript`, `stt_failed`, `tts_failed`, TTS audio는 Sprint 2.
텍스트 Sprint 1에서 `questionEnd`를 유지할지는 `PENDING_FE`.

WS path가 `interviewId` 기준인지 별도 `sessionId` 기준인지는 `PENDING_FE`.

## Turn 정책

- 기본 9턴.
- Sprint 1은 9턴 완료 시 종료. Director 조기 종료 없음.
- 첫 질문은 `hr_manager` 고정이고 evidence 없이 허용한다.
- 2턴부터 Director가 persona를 선택한다.
- `tech_lead` 목표 6턴, 최소 5턴.
- `domain_lead + hr_manager` 합산 최소 3턴.
- `domain_lead`와 `hr_manager` 사이 3턴 배분은 고정하지 않고 Director가 판단한다.

기술 질문은 모든 선택 repo를 균등하게 다루지 않는다. primary repo 1~2개 중심으로 근거 있는 꼬리질문 품질을 우선한다.

## Persona

- `tech_lead`: 코드, 아키텍처, 기술 판단, answer vs code 검증.
- `domain_lead`: 산업/서비스 도메인 관점. JD 요구사항 추궁이 아니라 domain question frame 기반.
- `hr_manager`: 긴장 완화, 협업, 기여도, 의사결정, 이전 답변 기반 follow-up.

Domain category:

- `finance`
- `game`
- `travel`
- `shopping`
- `medical`
- `mobility`
- `etc`

도메인별 question frame은 Sprint 1 기본 시드로 3개씩 둔다. 팀 검수 후 수정 가능해야 하므로 코드 하드코딩 금지.

## Evidence

질문 근거와 평가 근거를 분리한다.

- `question_basis`: 질문 생성 시 사용한 근거.
- `evaluation_basis`: 답변 평가/피드백/충돌 판정에 사용한 근거.

`tech_lead` 질문은 가능한 한 question evidence를 붙인다. `domain_lead`, `hr_manager`는 evidence 없는 질문도 가능하지만, 답변 분석(T3)에서 검증 가능한 주장이 나오면 Evidence Retriever로 후속 evidence를 찾아 `evaluation_basis`로 연결한다.

Sprint 1 Evidence Retriever 범위:

- README
- repository metadata
- languages
- commit metadata
- L2 deep analysis의 `notable_areas[].path` 주변 파일

전체 tree scan, 전역 keyword search, private repo 조회는 Sprint 1 제외.

## Conflict

`evidence_conflicts`는 Sprint 1에 포함한다. 용도는 `answer_vs_code`만이다.

- `turn_id`: 답변 turn.
- `evidence_id`: 충돌 근거.
- `claim_id`: `NULL`. Sprint 1에는 FK 없음.
- `source='answer_vs_code'`
- `claim_text`: 사용자 답변에서 추출한 주장 원문.
- `evidence_text`: 근거 스냅샷.
- `verdict='unresolved'`
- `resolution`: Sprint 2.

충돌이 발견되면 즉시 꼬리질문 후보로 사용한다. 질문은 단정하지 않고 확인형으로 생성한다.

## Redis Context Snapshot

Redis는 원본 저장소가 아니라 면접 진행용 작업 기억이다.

- M4-a 준비 시 초기 생성.
- T1 질문 생성 시 읽기.
- T4 Director 판단 이후 Postgres `context_state`와 함께 갱신.
- 기본 TTL 2시간.
- Redis에 없거나 만료되면 Postgres 원본에서 재구성한다.

원본은 PostgreSQL에 둔다: JD, repo analyses, notable areas, evidence, 질문/답변, report.
