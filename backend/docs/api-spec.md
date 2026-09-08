# API 스펙 — 원본 링크

⚠ **이 파일에 스펙을 복사하지 않는다.** API 표면의 유일한 진실은 FE 문서다.

→ [`frontend/docs/api-spec.md`](../../frontend/docs/api-spec.md)

응답 타입 대조 대상 → [`frontend/src/types/api.ts`](../../frontend/src/types/api.ts)

BE 가 구현하며 확정한 "계약 ↔ 데이터모델 충돌 9건" 은 [`becontext.md`](../../becontext.md) 1장에 있다.
스펙과 DB 가 어긋나 보일 때는 1장을 먼저 본다.

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
