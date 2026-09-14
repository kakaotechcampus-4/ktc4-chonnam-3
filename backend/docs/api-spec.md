# API 스펙 — 원본 링크

⚠ **이 파일에 스펙을 복사하지 않는다.** API 표면의 유일한 진실은 FE 문서다.

→ [`frontend/docs/api-spec.md`](../../frontend/docs/api-spec.md)

응답 타입 대조 대상 → [`frontend/src/types/api.ts`](../../frontend/src/types/api.ts)

BE 가 구현하며 확정한 "계약 ↔ 데이터모델 충돌" 결정은
[`db-schema.md`](db-schema.md) 의 "설계 초기안 대비 변경" 절에 있다.
스펙과 DB 가 어긋나 보일 때는 거기를 먼저 본다.

---

## FE 와 합의된 변경 — api-spec 보다 이쪽이 최신이다

BE 내부명을 그대로 쓰기로 했다 (경계 매핑 레이어 없음). `types/api.ts` 가 수정된다.

| api-spec / types 현재 | 확정 |
|---|---|
| `AgentRole = tech_lead \| senior_developer \| manager` | `tech_lead` / `hr_manager` / `domain_lead` |
| `StepKey` 4개 (`fetch_repos`/`extract_jd`/`match_score`/`prepare_result`) | 7개 — `doc_extract` / `repo_select` / `repo_detail` / `jd_fetch` / `jd_extract` / `repo_analyze` / `match_score` |
| `failureReason`: `jd_unreachable` / `jd_parse_failed` / `github_token_expired` | `jd_fetch_failed` / `jd_extraction_failed` / `token_invalid` |
| WS `answerStart` → 오디오 바이너리 → `answerEnd`, `question` 뒤 TTS, `transcript` / `stt_failed` / `tts_failed` | **스프린트1 은 양방향 텍스트.** STT/TTS 는 스프린트2 |

미결 — `analysis_jobs.status='partial'` 을 `RunStatus` 에 어떻게 싣나.
[error-reasons.md](error-reasons.md) 미결 절에 BE 권고가 있다.

---

## FE 작업 목록 — 수정 지점 (BE 조사분, 2026-09-08)

①②⑤ 는 **값 치환**이라 화면 코드에 영향이 없다. `frontend/src/features/*` 10개 파일이 전부
스켈레톤이고 `shared/api.ts` 도 아래 타입을 직접 쓰지 않아, union 정의만 바꾸면 컴파일이
깨질 곳이 없다 (`senior_developer` · `fetch_repos` 등 값 하드코딩 0건).

### `frontend/src/types/api.ts`

| 라인 | 현재 | 수정 |
|---|---|---|
| 6 | `StepKey` 4값 | `'doc_extract' \| 'repo_select' \| 'repo_detail' \| 'jd_fetch' \| 'jd_extract' \| 'repo_analyze' \| 'match_score'` |
| 9 | `AgentRole = 'tech_lead' \| 'senior_developer' \| 'manager'` | `'tech_lead' \| 'hr_manager' \| 'domain_lead'` |

- **⑤ 는 타입 수정 불필요** — 110행이 `failureReason: string | null` 로 열려 있다. 문서만 고치면 된다.
- 값을 쓰지 않고 참조만 하는 곳(자동 반영): `AgentRole` → 163 · 204 · 227, `StepKey` → 102 · 116.
- 4행 `PrepareStepKey` 는 그대로 유효하다 (`analyze_repo`/`build_persona`/`compose_question`/`set_criteria`).

### `frontend/docs/api-spec.md`

| 항목 | 라인 |
|---|---|
| ① `agentRole` · `senior_developer` | 26, 374, 395, 514, 520, 569 |
| ② `stepKey` · 예시 steps 배열 | 23, 238, 252–255, 266 |
| ⑤ `github_token_expired` · `jd_parse_failed` | 38, 146, 217, 233 |

### ③ 은 필드 수정이 아니다 ⚠

api-spec 410–447 이 `answerStart` → 오디오 바이너리 → `answerEnd` 이고 `types/api.ts` 187 에
`transcript` 메시지가 있다. 스프린트1 을 텍스트로 가면 **클라→서버 메시지 형태를 새로 정해야
한다** (예: `{ "type": "answer", "text": "..." }`). `transcript`(STT 결과 회신)도 텍스트
입력에서는 존재 이유가 없어진다. 값 치환이 아니라 프로토콜 합의가 필요하므로 별도 안건으로 둔다.

### ④ 는 결정 대기

`types/api.ts` 5행 `RunStatus`. BE 권고(union 유지 + 결과 응답에 카드 단위 정보)를 채택하면
이 줄은 건드리지 않는다.
