# task-09 — analysis 구현

> 필요: task-07 (`shared/api.ts`, 인증 가드, 재연동 배너)
> 근거: `spec/frontend/features/analysis.md`

## 목표

공고·문서 입력 → 분석 진행 → 레포 확정까지의 화면을 구현한다.

## 작업

- 공고 입력 폼 + URL 유효성 검사 (Wanted URL만 허용)
- 포트폴리오 파일 업로더 (드래그앤드롭, 형식·용량 검증) — 선택 즉시 `POST /documents/preview` 호출. Sprint 1에서 자소서는 preview POST 대상이 아니다.
- `/documents/preview`도 task-07의 세션 인증 실패 처리를 적용한다. `401 unauthenticated`이면 캐시 정리 후 로그인으로 이동하며 자동 재전송·401 재시도용 `FormData` 복제는 추가하지 않는다.
- `POST /analysis-runs` JSON 호출 (`postingUrl`, `documentId?`)
- `status: 'failed'` 시 "포트폴리오 없이 계속 진행" 확인 흐름 — 진행 시 `documentId` 생략
- 4-2-v2 체크리스트 + SSE 구독 — `EventSource` URL에 `/api` 프리픽스 직접 포함 (`shared/api.ts` 래퍼를 안 거침, `spec/frontend/architecture.md` "`/api` 프리픽스" 참고)
- `onerror` 시 `GET /analysis-runs/{runId}` 폴백 조회
- 4-3-v2 `failureReason` 9종 분기
- 5a-v2 레포 카드 컴포넌트
- 레포 카드 실패 상태 (회색 + `errorCode`)
- 공고 요구사항 리스트 (`category`: required/preferred/responsibility 3종 그룹핑, `displayOrder` 순서)
- 포트폴리오 매칭 안내 문구
- `내 레포 더 보기` — `GET /analysis-runs/{runId}/candidates?page=N`. `202 analyzing`이면 `retryAfter` 간격 폴링 후 카드 추가
- 선택 5개 상한 처리
- `selectedRepoIds`는 `result` 쿼리 응답 도착 후 1회만 초기화한다. 리렌더마다 재설정하면 사용자 선택이 덮어써진다
- `POST /interviews` 확정 호출

## 확인된 불일치 — 업로드 화면 수정 보류

2026-09-22 대화에서 사용자가 **업로드 형식·자소서 처리의 실제 수정을 보류**했다.

- 기존 명세는 포트폴리오만 preview 대상으로 받고 PDF·DOCX·TXT·MD를 허용한다. 현재 `JobInput.tsx`는 포트폴리오를 PDF로 제한하고 자소서도 업로드하며, 자소서 업로드·추출 확인 상태가 분석 시작을 막을 수 있지만 최종 요청에는 포트폴리오 ID만 보낸다.
- 위 화면 불일치만 후속 보완 대상으로 남긴다. 포트폴리오 20MB 기준은 이미 확정됐고 화면·모의 서버의 상한도 맞췄으므로 용량을 다시 결정하지 않는다. 이번 문서 정리는 화면 코드를 수정하거나 보류를 해제하지 않는다.

## 저장소 선택 조건

2026-09-22 사용자 요청으로 수정을 보류했다가, 2026-11-04 부분 실패 run의 진행 경로를 열면서 보류를 해제했다.

- [서버 선택 기준](../../spec/backend/features/analysis-run.md#선택-가능-조건)은 L1 분석 `succeeded`만 허용하며, [개발용 모의 서버](../src/mocks/handlers/interview.ts)도 `partial` 선택을 거절한다.
- [RepoSelect.tsx](../src/features/analysis/RepoSelect.tsx)는 `succeeded` 카드만 선택할 수 있게 하고, 기본 선택도 `succeeded`인 추천 레포만 둔다. `partial`·`failed` 카드는 회색과 `errorCode` 문구로 보여 주고 선택을 막는다.
- DB 구조·API 필드를 추가하지 않는다. 분석 run 전체의 부분 실패 처리와는 구분한다.

## 부분 실패 후 성공 결과 이동 경로

2026-09-22 사용자 요청으로 보완 필요 항목으로만 표시했다가, 2026-11-04 README 없는 저장소 하나로도 run 전체가 partial이 되어 면접을 시작할 수 없는 문제를 확인하고 보류를 해제했다.

- 기존 [부분 실패 기준](../../spec/backend/features/analysis-run.md#부분-실패)은 DB `partial` → FE `failed`이며 성공 결과는 조회할 수 있다. 이 기준과 API는 변경하지 않는다.
- [AnalysisFailed.tsx](../src/features/analysis/AnalysisFailed.tsx)는 result API 조회가 성공하고 `succeeded` 저장소가 1개 이상이면 버튼을 거치지 않고 실패 안내 없이 기존 저장소 선택 화면으로 바로 이동한다. [RepoSelect.tsx](../src/features/analysis/RepoSelect.tsx)는 선택할 수 없는 카드가 있으면 “일부 레포는 분석하지 못했어요. 흐리게 표시된 레포는 선택할 수 없어요.”를 보여 준다. 결과가 없는 실패 run은 result API가 `409 not_ready`라 실패 화면에 남는다. 화면 기준은 [분석 명세](../../spec/frontend/features/analysis.md)를 따른다.
- 모의 서버는 BE처럼 결과가 없는 실패 run의 result 조회를 `409 not_ready`로 응답하고, 부분 실패 run seed(`SEED_PARTIAL_RUN_ID`)로 두 경우를 재현한다.
- 실제 BE·GitHub와의 연결 확인은 별도로 한다.

## 완료 조건

- [ ] 공고 입력 폼 + URL 유효성 검사
- [ ] 포트폴리오 파일 업로더 (드래그앤드롭, 형식·용량 검증)
- [ ] `POST /documents/preview` 호출 + 401 세션 만료 시 캐시 정리·로그인 이동
- [ ] `status: 'failed'` 포트폴리오 없이 계속 진행 확인 흐름
- [ ] `POST /analysis-runs` JSON 호출
- [ ] 4-2-v2 체크리스트 + SSE 구독
- [ ] `onerror` 시 상태 폴백 조회
- [ ] 4-3-v2 `failureReason` 9종 분기
- [ ] 5a-v2 레포 카드 컴포넌트
- [ ] 레포 카드 실패 상태 (회색 + errorCode)
- [ ] 공고 요구사항 리스트 (`category` 3종 그룹핑, `displayOrder` 순서)
- [ ] 포트폴리오 매칭 안내 문구
- [ ] `내 레포 더 보기` — candidates 페이지네이션 + 202 폴링
- [ ] 선택 5개 상한 처리
- [ ] `POST /interviews` 확정 호출
- [ ] `npm run build` 통과
- [ ] `npm run lint` 통과

## 커밋

```
feat: add job analysis and repository selection flow
```
