# AI 의사결정 대기 목록

갱신일: 2026-09-12. 상태: 남은 공동 결정과 후속 검토만 관리.

확정한 내용은 이 파일에서 제거하고 [AI 결정 기록](spec/ai/decisions/README.md)과 해당 기능 명세에 보존한다. 아래 항목은 각 주제의 **아직 결정하지 않은 부분**이며, 연결된 결정 문서 전체가 미승인이라는 뜻은 아니다.

## 읽는 방법

- 기존 FIX와 Accepted 범위는 해당 원본을 따른다. 이 목록으로 Proposed 계약을 자동 승인하지 않는다.
- 검토 역할은 합의가 필요한 파트이며 실제 담당자 배정·검수 완료를 뜻하지 않는다.
- 관련 구현 전에 필요한 결정은 그 시점에 해결한다. 모든 항목을 Sprint 2로 미루지 않는다.
- 독립 정책·합성 fixture 작업은 [AI 작업 지도](ai/docs/pipeline.md)에 따라 진행한다. 일반 구현·테스트·전달 확인은 새 의사결정으로 추가하지 않는다.
- 항목의 일부가 결정되면 그 부분만 삭제한다. 전체가 해결되면 항목을 삭제하고, 남은 ID는 재번호화하거나 재사용하지 않는다.

| 구분 | 항목 | 결정이 필요한 시점 |
| --- | --- | --- |
| 내부 AI·분석 연결 | AI-L01~AI-L10 | 관련 계약·실제 호출·분석 연결 전 |
| BE·FE·리포트 연결 | AI-L11~AI-L17 | 해당 저장·전송·공개 응답 구현 전 |
| 자료 운영·평가·검색 | AI-L18~AI-L20 | 실제 자료 수집·최종 평가·검색 확장 전 |
| 후속 기능 | AI-L21~AI-L26 | 해당 기능의 채택·착수 전 |

## 내부 AI·분석 연결

### AI-L01. 실제 모델 공급자와 API 식별자

- 검토·시점: AI·BE, 실제 LLM 연결 전.
- 남은 결정: 프로젝트 표기 `5.5 Luna`에 대응하는 provider, 호출 가능한 model ID, 인증 설정, 지원 기능, 모델 버전 기록 방식과 현재 SDK/client의 적합성.
- 근거: [내부 계약](spec/ai/contracts.md), [ForAI 2·6](ForAI.md), [기준 결정](spec/ai/decisions/0001-ai-baseline.md).

### AI-L02. 내부 입출력과 저장 계약 채택

- 검토·시점: AI·BE, 공개 필드 영향 시 FE; 해당 schema·저장 구현 전. 상태: Proposed 검토.
- 남은 결정: Context, Question/Question Contract, AnswerAnalysis, DirectorDecision, Evidence/ToolResult, feedback의 정확한 필드·enum·null·schema version·참조 방식. analysis/decision/Contract의 컬럼·JSONB 위치와 공개 API 변환 책임.
- 근거: [내부 계약](spec/ai/contracts.md), [Context](spec/ai/features/job-context.md), [리포트](spec/ai/features/report-profile.md).

### AI-L03. 변환·요약의 version과 저장 매핑

- 검토·시점: AI·BE, JD·L1·프로필의 실제 저장·실행 연결 전.
- 남은 결정: deterministic 변환 version·출처 기록, `role_summary` 필드명·저장/API 매핑. 프로필 집계 단위·중복 제거·job 인수·저장 방식은 AI-L17에서 함께 결정.
- 근거: [0006 결정](spec/ai/decisions/0006-task-llm-usage-policy.md), [내부 계약](spec/ai/contracts.md), [레포 분석](spec/ai/features/repository-analysis.md), [프로필](spec/ai/features/report-profile.md).

### AI-L04. 실행 상한과 재시도 책임

- 검토·시점: AI·BE, 실제 호출·Director loop 연결 전.
- 남은 결정: task별 timeout·입력/token·Context 길이·동시성·Tool·재작성·재계획 budget, 소진 후 서비스 처리, SDK/gateway/task/worker 중 attempt 관리 주체. L1 실패 item 재호출의 총 attempt 계산과 의미 검증 실패의 재호출 여부·attempt 차감·외부 실패 매핑.
- 근거: [0008 후보 정책](spec/ai/decisions/0008-ai-candidate-policy.md), [Gateway와 실패](spec/ai/contracts.md), [면접](spec/ai/features/interviewer.md), [L1 배치](spec/ai/features/repository-analysis.md).

### AI-L05. JD 신호와 분석 7단계의 선행관계

- 검토·시점: AI·BE, 진행 표시 영향 시 FE; candidate ranking 연결 전.
- 남은 결정: `repo_select`가 JD 수집보다 앞선 기존 순서에서 첫 batch의 `jd_signal`을 얻는 방법. JD 선확보·외부 단계 표시 분리, 첫 batch 신호 사용 조정, 단계 계약 변경 중 채택안.
- 근거: [분석 단계 순서 보류](spec/ai/features/repository-analysis.md), [BE pipeline](backend/docs/pipeline.md).

### AI-L06. L2 부분 결과의 준비 성공·지원 범위 계약

- 검토·시점: AI·BE, L2 결과를 면접 준비 완료로 연결하기 전.
- 남은 결정: notable area 일부가 무효일 때 전체 실패 또는 검증된 1~5개 subset 성공을 허용할 조건. 실제 지원 언어·도구 목록과 읽기 범위, 한계를 표현할 계약 필드, repo 분석 상태와 `preparing_failed` 매핑.
- 근거: [0008 후보 정책](spec/ai/decisions/0008-ai-candidate-policy.md), [레포 분석](spec/ai/features/repository-analysis.md), [준비 조건](spec/ai/features/interviewer.md), [검증](spec/ai/verification.md).

### AI-L07. 추천 점수와 미계산 표시

- 검토·시점: AI·BE·FE, 추천 저장·카드 정렬 연결 전.
- 남은 결정: match score 산식·스케일·정렬·동점 처리, 점수 미계산/분석 실패의 표현, 추천 이유·requirement 연결과 저장·FE 표시.
- 근거: [추천](spec/ai/features/repository-analysis.md), [OpenAPI](spec/shared/contracts/openapi.yaml).

### AI-L08. 제한 검색의 실행 범위와 운영 계약

- 검토·시점: AI·BE, 실제 Evidence Tool 연결 전.
- 남은 결정: notable area가 디렉터리일 때 파일 열거 방법, 주변 파일 범위·깊이·개수·byte/token/time 상한. 실제 상태 필드·enum·저장은 AI-L02, 실행 budget·재시도 책임은 AI-L04와 함께 결정.
- 근거: [0003 조회 정책](spec/ai/decisions/0003-evidence-lookup-policy.md), [0008 후보 정책](spec/ai/decisions/0008-ai-candidate-policy.md), [근거 검색](spec/ai/features/evidence-retrieval.md).

### AI-L09. 질문 복구의 서비스 연결과 턴 배분

- 검토·시점: AI·BE·FE와 평가 담당, 후보 판단을 서비스 복구·Director에 연결하기 전.
- 남은 결정: 재작성·재계획·유효 후보 없음의 실제 반환 계약과 BE/FE 상태 전이, 사용자 입력 복구 조건·전달 방식. HR·domain 각각의 최소 횟수·교대 규칙. 상태·저장·Question Contract는 AI-L02, 공개 점수는 AI-L15와 함께 결정.
- 근거: [0004 정성 평가](spec/ai/decisions/0004-answer-assessment-policy.md), [0008 후보 정책](spec/ai/decisions/0008-ai-candidate-policy.md), [답변 평가](spec/ai/features/answer-evaluation.md), [면접](spec/ai/features/interviewer.md).

### AI-L10. 도메인 운영 문구·입력·seed 채택

- 검토·시점: AI·도메인 검수 담당·BE, 운영 seed 설치 전.
- 남은 결정: 운영 문구의 최종 채택·수정과 독립·도메인 검수, category 선택 근거·신뢰 판단의 실제 입력 계약, 활성 version·검토 metadata·저장·변경 반영 방식.
- 근거: [0005 도메인 정책](spec/ai/decisions/0005-domain-question-policy.md), [0008 후보 정책](spec/ai/decisions/0008-ai-candidate-policy.md), [도메인 프레임](spec/ai/features/domain-frames.md).

## BE·FE·리포트 연결

### AI-L11. Worker 인수와 실행 배치

- 검토·시점: AI·BE, worker 등록·호출 연결 전. 상태: Proposed 검토.
- 남은 결정: 기존 6개 job의 정확한 함수 signature·직렬화 인수·timeout과 retry 경계, 답변별 ARQ job 여부, 준비/면접 Worker의 물리적 분리 여부.
- 근거: [Context](spec/ai/features/job-context.md), [아키텍처](spec/ai/architecture.md), [BE pipeline](backend/docs/pipeline.md).

### AI-L12. 저장·큐·알림의 중복 방지

- 검토·시점: AI·BE, 외부 호출과 DB 상태 전이 연결 전.
- 남은 결정: transaction 분리, row lock/CAS·lock token, 입력 버전 비교, 저장 성공·enqueue 실패 복구, outbox 필요 여부, 동일 answer_vs_code 충돌의 중복 방지 키/제약.
- 근거: [Context](spec/ai/features/job-context.md), [면접](spec/ai/features/interviewer.md), [충돌 저장](spec/ai/features/evidence-retrieval.md).

### AI-L13. WS 식별자·메시지·인증 연결

- 검토·시점: FE·BE, AI payload는 AI도 참여; 실제 WS 연결 전. 상태: PENDING_FE 및 payload 검토.
- 남은 결정: interviewId/sessionId 경로, 질문 payload와 `answerReceived` 저장 확인 의미, 텍스트 `questionEnd` 유지 여부, 사용자 종료 wire, WS 인증과 공통 JWT 전달 방식.
- 근거: [면접 공개 메시지](spec/ai/features/interviewer.md), [이관 상태](spec/shared/contracts/migration.md), [원본 검토](spec/ai/source-audit.md).

### AI-L14. 제출 식별·준비 상태·재연결

- 검토·시점: FE·BE·AI, 준비/새로고침/복구 연결 전. 상태: PENDING_FE 및 계약 차이 검토.
- 남은 결정: 지연된 이전 답변을 식별할 제출 ID/Turn ID, reconnect·heartbeat·abandoned 판정, prepare retry와 `answerMode`/`lastError` snapshot, 준비 단계 표시 순서, StepStatus 성공값 매핑.
- 근거: [면접](spec/ai/features/interviewer.md), [FE/계약 차이](spec/ai/source-audit.md), [검증](spec/ai/verification.md).

### AI-L15. 리포트 점수와 공개 응답

- 검토·시점: 팀 평가 담당·AI·BE·FE, 실제 리포트 200 공개 전. 상태: PENDING_TEAM.
- 남은 결정: 점수 기준·스케일·가중치·합산·미관찰 처리와 `score_criteria` seed, 필수 숫자 계약 유지 또는 nullable/status 변경. FE의 score key·headline·coverage·상세 근거 요구와 공개 필드.
- 근거: [리포트](spec/ai/features/report-profile.md), [OpenAPI](spec/shared/contracts/openapi.yaml), [ForAI 5](ForAI.md).

### AI-L16. 리포트 생성 가능 상태와 재시도

- 검토·시점: BE·AI, 사용자 상태 표시는 FE; lazy report job 연결 전.
- 남은 결정: completed/abandoned 등에서 생성 가능한 조건, 실패 attempt의 영구 저장 책임, lock 만료 후 이전 worker 판정, 재enqueue·중복 저장·이전 성공본 보존 방식.
- 근거: [리포트](spec/ai/features/report-profile.md), [기준 결정](spec/ai/decisions/0001-ai-baseline.md).

### AI-L17. 프로필 집계 단위와 갱신

- 검토·시점: AI·BE, profile_summary job 연결 전.
- 남은 결정: 같은 repo를 여러 완료 면접에서 사용한 경우 집계 단위·중복 제거·갱신 시점, 정확한 저장 key·job 인수와 실패/이전 성공본 유지 방식.
- 근거: [0006 결정](spec/ai/decisions/0006-task-llm-usage-policy.md), [프로필](spec/ai/features/report-profile.md), [Context](spec/ai/features/job-context.md).

## 자료 운영·평가·검색

### AI-L18. 원문·호출 기록·정정의 운영 정책

- 검토·시점: AI·BE·팀 운영 담당, 실제 사용자 자료 수집·raw output 보존 전.
- 남은 결정: task별 실패 원문 저장 위치, 접근권한·마스킹·보존/삭제, 호출 metadata 수집 범위, 평가 재사용 동의·배포 형태, 자료 삭제가 분석·리포트에 미치는 영향, 원문을 보존하는 정정·재생성 이력. 음성은 AI-L21, 문서 Claim은 AI-L22와 함께 결정.
- 근거: [내부 계약](spec/ai/contracts.md), [리포트](spec/ai/features/report-profile.md), [검증](spec/ai/verification.md).

### AI-L19. 실제 평가자료·운영 형식·수용 기준

- 검토·시점: AI·평가 담당·팀, 실제 자료 운영·최종 모델 평가·출시 판정 전.
- 남은 결정: 최종 사례 수·유형별 비율·split 비율, 실제 자료·기대 결과 검수와 불일치 해결 담당 배정, 채점기의 실제 신뢰성 검증, 정확도·오류·latency·비용·동시성 목표·실행 조건·출시 기준. 실제 자료의 운영 schema·저장·배포와 사용 권한은 AI-L18과 함께 결정.
- 근거: [0007 평가 원칙](spec/ai/decisions/0007-evaluation-design-policy.md), [0009 평가 방법](spec/ai/decisions/0009-ai-evaluation-method.md), [검증](spec/ai/verification.md).

### AI-L20. 후속 vector·검색 범위 도입

- 검토·시점: AI·BE·팀, Sprint 2 검색 확장 채택·착수 전.
- 남은 결정: Sprint 2 도입 여부·대상 task·효용/비용 채택 기준, embedding model·dimension·chunk·재색인·저장소, full tree/global search 확장 여부·시점.
- 근거: [0002 결정과 BE 반영 확인](spec/ai/decisions/0002-sprint1-vector-search.md), [0009 평가 방법](spec/ai/decisions/0009-ai-evaluation-method.md), [근거 검색](spec/ai/features/evidence-retrieval.md), [이관 상태](spec/shared/contracts/migration.md).

## 후속 기능

아래 항목은 채택된 구현 backlog나 담당 배정이 아니다. 기능별 채택 여부·범위·일정·소유자를 승인된 Sprint 2 계획과 먼저 맞춘다. 기존 단계 구분과 제약은 [후속 기능 명세](spec/ai/features/extensions.md)를 따른다.

### AI-L21. 음성 입력·출력과 보존

- 검토·시점: AI·FE·BE·팀, Sprint 2 음성 착수 전.
- 남은 결정: realtime 또는 STT/TTS 조합, provider/model·Persona별 voice ID, 오디오 형식·길이·저장/삭제/다시 듣기, 전사 확인·수정·재녹음, 텍스트 병행/전환, 브라우저 상태·wire·실패 복구.
- 근거: [후속 기능](spec/ai/features/extensions.md), [원본 검토](spec/ai/source-audit.md).

### AI-L22. 문서 Claim과 문서·코드 충돌

- 검토·시점: AI·BE·FE, Sprint 2 Claim 추출·사용 전.
- 남은 결정: Claim schema·추출/사용 시점·원문 위치·version·검증 상태, 사용자 확인/수정/제외, document_claims FK·보존, 문서 conflict source·처리·API.
- 근거: [후속 Claim](spec/ai/features/extensions.md), [기준 결정](spec/ai/decisions/0001-ai-baseline.md).

### AI-L23. 외부 도메인 자료 조회

- 검토·시점: AI·자료 검수 담당·BE, Sprint 2 Domain Knowledge 조회 전.
- 남은 결정: 자료 출처·사용 권한·지역·기준 시점·검수자, corpus/공개 검색/DB/vector 방식, 갱신 주기·적용 조건·인용·미지원 처리. vector 선택은 AI-L20과 연결.
- 근거: [외부 도메인 자료](spec/ai/features/extensions.md), [도메인 프레임](spec/ai/features/domain-frames.md).

### AI-L24. 공고 URL의 이미지 판독

- 검토·시점: AI·BE·FE, Sprint 2 이미지 공고 처리 전.
- 남은 결정: 동일 공고 URL 경로에서 지원할 이미지·format·OCR provider, 텍스트와 이미지의 충돌·누락·품질 판정, 실패 reason·원문 보존·동의.
- 근거: [이미지 입력 경계](spec/ai/features/extensions.md).

### AI-L25. 리포트 이의 제기와 재평가

- 검토·시점: 팀·AI·BE·FE, Sprint 2 이의 제기 기능 전.
- 남은 결정: 제출 단위·Persona 식별·중복 방지, 검토 책임·응답 기한·상태, 원문·평가·점수에 미치는 영향, 재채점·재생성 허용 범위.
- 근거: [이의 제기 경계](spec/ai/features/extensions.md), [리포트](spec/ai/features/report-profile.md).

### AI-L26. 실측에 따른 Sprint 2 모델·검색 전략 선택

- 검토·시점: AI·팀, 인프라 영향 시 BE; 모델 분리·음성·검색 조합 변경 전.
- 남은 결정: 실제 비교 결과에 따른 단일 모델 유지 또는 task별 분리, 고비용 task 개선안, vector 도입 시 prompt 구성과 버전·캐시 변경. 음성 선택은 AI-L21, vector는 AI-L20과 연결.
- 근거: [0009 평가 방법](spec/ai/decisions/0009-ai-evaluation-method.md), [ForAI 6](ForAI.md), [내부 계약](spec/ai/contracts.md), [검증](spec/ai/verification.md).

## 결정 후 정리

1. 해당 기능 명세와 결정 문서에 결정 결과, 실제 결정자, 날짜, 근거 문서/PR을 기록한다. 기존 결정 이력은 삭제하지 않는다.
2. 영향을 받는 계약·작업 가이드·검증 조건을 함께 갱신한다. 공통 API·DB 변경은 관련 팀의 승인 범위를 확인한다.
3. 이 파일에서 확정한 부분을 삭제한다. 남은 질문이 없으면 항목 전체를 삭제하고 참조는 결정 문서로 연결한다.
4. 제안, 담당 배정, 문서 작성과 실제 검수·구현·실측 완료를 구분한다. 미결정 항목을 삭제해 합의된 것처럼 만들지 않는다.
