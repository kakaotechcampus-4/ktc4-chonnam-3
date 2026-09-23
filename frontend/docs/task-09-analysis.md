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

## 확인된 불일치 — 저장소 선택 조건 수정 보류

2026-09-22 사용자 요청에 따라 **항목만 기록하고 실제 수정은 보류**한다.

- 현재 [RepoSelect.tsx](../src/features/analysis/RepoSelect.tsx)는 `failed`만 선택을 막아 `partial` 저장소도 선택할 수 있다. 기본 선택도 `recommended`만 확인한다.
- 기존 [서버 선택 기준](../../spec/backend/features/analysis-run.md#선택-가능-조건)은 L1 분석 `succeeded`만 허용하며, [개발용 모의 서버](../src/mocks/handlers/interview.ts)도 `partial` 선택을 거절한다.
- 후속 보완 대상은 화면의 수동·기본 선택과 제출 시 선택값 확인, 선택 불가 안내다. 성공한 저장소만 선택하도록 기존 기준에 맞추며 DB 구조·API 필드를 추가하지 않는다.
- 이번에는 화면 코드·모의 서버·API 계약을 변경하지 않는다. 실제 BE의 선택 조건 구현·검증 완료를 뜻하지도 않는다. 분석 run 전체의 부분 실패 처리와는 구분한다.

## 확인된 누락 — 부분 실패 후 성공 결과 이동 경로 보완 보류

2026-09-22 사용자 요청에 따라 **보완 필요 항목으로 표시하고 실제 수정은 보류**한다.

- 기존 [부분 실패 기준](../../spec/backend/features/analysis-run.md#부분-실패)은 DB `partial` → FE `failed`이며 성공 결과는 조회할 수 있다. 이 기준을 새로 변경하지 않는다.
- 현재 [AnalysisFailed.tsx](../src/features/analysis/AnalysisFailed.tsx)에는 성공 결과 조회·저장소 선택 화면으로 이어지는 경로가 없다. 같은 날 확인한 [PR #52](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/52)의 `c195e4a004ff533ffea9e885848b3487d47ef45c`에서도 해당 화면은 로컬과 동일하다.
- 후속 보완안: 조회 가능한 성공 결과가 있을 때 기존 실패 안내 화면에 “분석에 성공한 저장소 보기” 버튼을 두고 기존 저장소 선택 화면으로 연결한다. 기존 결과 조회 API를 활용하며 새 DB 구조·API 필드는 추가하지 않는 방향이다. 이번에는 이 제안만 기록한다.
- 전체 run의 일부 저장소가 실패했을 때 성공한 저장소를 활용하는 문제다. 위의 개별 `partial` 저장소 선택 제한과는 별개이며, 그 수정 보류 상태도 유지한다.
- 화면 코드·API 계약·원격 PR은 변경하지 않는다. 실제 기능 구현·연결·검증 완료로 처리하지 않는다.

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
