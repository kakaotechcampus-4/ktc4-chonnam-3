# DEVON 용어 원본

상태: Sprint 1 FIX.

| 용어 | 의미 | 경계 |
| --- | --- | --- |
| Repository | 사용자의 public GitHub 저장소 | 코드의 `queries.py`와 혼동하지 않는다 |
| JobPosting | 사용자가 입력한 채용 공고 | Sprint 1은 Wanted만 지원 |
| JD Requirement | 공고에서 추출한 요구사항 | Wanted 구조화 필드를 우선 신뢰 |
| AnalysisRun | 공고와 repo 후보를 분석하는 실행 단위 | 내부 job status와 FE RunStatus는 매핑될 수 있다 |
| Candidate | 특정 AnalysisRun에서 선택/추천 후보가 된 repo | `analysis_repo_candidates`에 run 종속 ranking 저장 |
| Interview | 질문/답변/평가가 연결된 면접 기록 | 영구 식별자는 `interviewId` |
| Realtime Session | WS 연결과 단일 접속 lock을 위한 실시간 연결 단위 | `sessionId` 별도 유지 여부는 `PENDING_FE` |
| Persona | Director가 취하는 질문 관점 | 독립 Agent가 아니다 |
| Director | 다음 persona, 질문, follow-up을 결정하는 단일 면접 제어자 | Evidence Retriever는 Director tool |
| Evidence | 코드/README/metadata/commit에서 확인한 질문 또는 평가 근거 | 원본과 요약, git ref를 보존한다 |
| Conflict | 사용자 답변/문서 주장과 evidence가 충돌하는 기록 | Sprint 1은 `answer_vs_code`만 사용 |
| Report | 면접 종료 후 생성되는 결과/피드백 | 점수 산정 근거는 `PENDING_TEAM` |

## Persona

- `tech_lead`: 코드, 아키텍처, 기술 판단, answer vs code 검증.
- `hr_manager`: 긴장 완화, 협업, 기여도, 의사결정, 이전 답변 기반 follow-up.
- `domain_lead`: 산업/서비스 도메인 관점. JD 요구사항 추궁이 아니라 domain question frame 기반.

## Domain Category

- `finance`
- `game`
- `travel`
- `shopping`
- `medical`
- `mobility`
- `etc`
