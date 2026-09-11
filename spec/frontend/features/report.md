# report

상태: 초안 — frontend/md/features/report.md에서 이관.

## 목표 + 화면 구성

면접 결과를 3개 탭으로 보여주고 재도전을 받는다.

피드백 이의 제기는 `spec/shared/contracts/migration.md`("Report disagreement | Sprint 1 테이블 생성, API/row 생성은 Sprint 2 | FIX")에 따라 **Sprint 2 기능**이다. Sprint 1은 버튼만 배치하고 항상 비활성(disabled) 상태로 둔다 — `POST /reports/{id}/feedback-disagreements` 호출 자체를 만들지 않는다.

| 화면 | 코드 | 구성 |
| --- | --- | --- |
| 리포트 | 5c-v2 | 탭 3개 + `재도전` 버튼 |
| 리포트 생성 중 | 5c-v2 | 생성 중 안내 + 폴링 |

### 탭 구조

| 탭 | 필드 |
| --- | --- |
| 종합리포트 | `headline` · `totalScore` · `summary` · `scores` · `coverage` |
| 면접관별 피드백 | `agentFeedbacks` |
| 면접 기록 | `turns` |

### 종합리포트 탭

- `headline` — 한 줄 총평
- `totalScore` — 총점
- `summary` — 요약 문단
- `scores` — 6개 고정 (`project_understanding` · `technical_reasoning` · `problem_solving` · `communication` · `contribution_clarity` · `company_job_fit`). `label`은 서버가 내려준 한글 라벨을 그대로 사용
- `coverage` — "요구사항 8개 중 5개가 다뤄짐" + `uncoveredRequirements` 목록. `company_job_fit` 점수의 근거로 함께 표시

### 면접관별 피드백 탭

`agentFeedbacks` 3개 고정 (`tech_lead` · `hr_manager` · `domain_lead`)

| 요소 | 필드 |
| --- | --- |
| 태그 | `tags[]` |
| 강점 | `strengths[]` |
| 개선점 | `improvements[]` |
| 이의 제기 버튼 | Sprint 1: 항상 비활성. Sprint 2 API 준비되면 `disagreementSubmitted`로 활성/비활성 결정 |

### 이의 제기 모달 (Sprint 2 — 지금 구현 대상 아님)

모달 자체는 만들지 않는다. 아래는 Sprint 2 착수 시 그대로 쓸 설계 메모다.

| 항목 | 내용 |
| --- | --- |
| 사유 (필수) | `factual_error` 사실과 다름 / `insufficient_basis` 근거 부족 / `overly_harsh` 과도한 평가 / `unclear_intent` 질문 의도 불명확 / `other` 기타 |
| 코멘트 (선택) | 최대 500자 |

제출 단위는 `(reportId, persona)`다. persona당 1회만 가능.

## 화면 이동 순서

```
5b-v2 interviewEnd  → 5c-v2
/home 최근 면접 클릭 → 5c-v2
마이페이지 [리포트 보기] → 5c-v2

5c-v2
  ├─ 탭 전환 (종합 / 면접관별 / 면접 기록)
  ├─ [이의 제기] → 비활성 (Sprint 2)
  └─ [재도전]    → POST /interviews/{id}/retry → 201 → /interview/{newId}/prepare (5a2-v2)
```

## API 연동

| # | 엔드포인트 | queryKey |
| --- | --- | --- |
| 19 | `GET /interviews/{id}/report` | `['interview', id, 'report']` |
| 20 | `POST /interviews/{id}/retry` | — |

`21 POST /reports/{id}/feedback-disagreements`는 Sprint 2 전까지 호출하지 않는다(아래 참고).

`['interview', id]`를 무효화하면 하위 `report`까지 함께 무효화된다.

### GET /interviews/{id}/report

| 코드 | 응답 | 처리 |
| --- | --- | --- |
| 200 | 리포트 본문 | 렌더 |
| 202 | `{ status: "generating", retryAfter: 3 }` | `retryAfter` 간격으로 폴링 |
| 409 | `report_unavailable` | 진행된 턴 0개. 리포트 없이 안내 |

`retryAfter`는 optional이므로 값이 없을 때의 기본 간격을 정해둔다.

### POST /interviews/{id}/retry

원본 세션의 `runId`·레포 조합을 복사해 새 세션을 만든다. Request 본문 없음.

```json
{ "sessionId": "sess_new456", "interviewId": "iv_002" }
```

| 코드 | reason | 처리 |
| --- | --- | --- |
| 409 | `original_not_completed` | 원본이 완료 상태가 아님 |
| 409 | `repository_unavailable` | 원본 레포가 삭제·private 전환됨 |
| 409 | `session_limit_exceeded` | 동시 세션 상한 |
| 410 | `run_expired` | 분석 결과 만료. 처음부터 다시 |

성공 시 `interviews` 캐시 무효화 후 `/interview/{interviewId}/prepare`로 이동.

### POST /reports/{id}/feedback-disagreements (Sprint 2 — 지금 구현 대상 아님)

```json
{
  "persona": "tech_lead",
  "reasonType": "factual_error",
  "comment": "TTL 근거를 설명했는데 반영되지 않았습니다."
}
```

| 코드 | reason |
| --- | --- |
| 204 | — |
| 409 | `already_submitted` |

성공 시 `interview(id).report` 무효화. (Sprint 2 착수 시 참고용 설계 메모)

### 캐시

| 시점 | 무효화 |
| --- | --- |
| 면접 완료 (리포트 생성) | `home`, `interviews` |
| 재도전 | `interviews` |

리포트는 생성 후 바뀌지 않으므로 `staleTime`을 길게 잡을 수 있다.

## 상태 요구사항

| 상태 | 용도 |
| --- | --- |
| `activeTab` | `overview` / `feedbacks` / `transcript` |

`activeTab`은 URL 쿼리와 동기화하면 새로고침·공유 시 탭이 유지된다.

`disagreementModal`/`selectedReasonType`/`comment`/제출 관련 상태는 Sprint 2 항목이다 — Sprint 1은 버튼이 항상 비활성이라 모달 자체가 열리지 않는다.

## 검증 시나리오

- 202 `generating` 폴링 동작
- 409 `report_unavailable` empty state
- `scores` 6개 + `coverage` 정상 렌더
- 이의 제기 버튼이 항상 비활성인지 확인 (Sprint 1)
- 재도전 409/410 분기 확인
