# Director 개선의 공개 발췌 근거

이 묶음은 2026-11-11 A~L 개발 실험의 원본에서 선택한 근거다. 상세 문제·선택·변경·실행 이력은 [구현 기록](../../../../spec/ai/implementation.md)과 [레퍼런스 이슈 #269](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/269)에 모은다. 이 README는 자료 형식과 재검산 범위만 설명한다.

## 파일과 형식

JSON은 UTF-8이며 각 파일의 `schema`로 형식을 구분한다. A/B는 각 실험의 이전/후보 정책이며, 서로 다른 실험의 A/B를 같은 버전이나 독립 표본으로 합치지 않는다.

| 파일 | 내용 |
| --- | --- |
| `summary.json` | 중복 대조한 A~L 물리 호출의 cohort 합계, 사용량·설정 기록 완전성, 실제/Mock 분리 |
| `criteria.json` | L 실행 전에 동결한 PS main의 의미 적합성 기준과 공개 코드 출처 |
| `semantic-fit-cases.json` | 한 개발 문맥의 고정 후보12개, 사전 oracle, 실제 A/B Review24개와 Codex 대조 |
| `semantic-fit-generation.json` | 실제 생성2개와 비PS main/과거 미답 follow_up 범위2개를 A/B 비교한8호출 |
| `answer-scope-cases.json` | 합성 답변2개의 사실/제안 구간4호출과 별도 기여 범위 보완1호출 |
| `review-calibration-cases.json` | J의 부적합4·정상4 후보에 대한 실제 Review16개 |
| `service-flow-summary.json` | K의 실제 BE 함수·격리 PostgreSQL·Luna9턴 요약, 합성 문답, 원분석·재실행·시간 |
| `provenance.json` | 원본의 식별 해시·공개 파일 해시·선택/ID 변환 범위 |
| `verify.py` | 공개한 값의 해시·분모·판정 분류·인용·합계 재검산. 표준 라이브러리만 사용 |

`raw_review`는 모델이 실제 반환한5개 flag·짧은 검토 사유·질문 인용이다. `codex_source_grade`와 oracle은 Codex의 원문 대조다. 전문가의 독립 사람 검수나 모델의 비공개 내부 추론이 아니다. false·unknown·실패·거절도 원래 판단대로 남겼다.

UUID는 묶음 안에서만 연결되는 `public-ref-NNN`으로 바꾸고 개인 계정·비밀 설정·인증 정보·실제 사용자의 음성/면접 답변·전체 SSE를 제외했다. 원문의 질문/합성 답변·판정·수치는 수정하지 않았다. 공개된 선택 JSON은 원래 전체 HTTP body와 바이트가 같지 않다.

## 재검산

저장소 루트에서 실행한다. 패키지 설치·네트워크·모델·업무 DB 연결은 발생하지 않는다.

```text
python ai/evals/evidence/director-improvement-20261111/verify.py
```

검사기는 공개 파일9개의 SHA256, cohort 호출/토큰 합계, L12쌍의6/12→12/12와 잘못된 승인6→0, 정상6개 보존, J8쌍의4/8→8/8, 범위2쌍, 직접 질문의 연속 인용, 합성 답변 내 주장 구간, 실제/Mock 분모, K9턴과27물리 호출·시간 합계를 다시 계산한다. `provenance.json` 자체는 Git commit에 고정하며 자기 참조 해시를 주장하지 않는다.

## 검산의 한계

- 원본 장부의 call_id·원래 전체 payload·DB snapshot·전체 답변 분석을 모두 공개하지 않았다. 해당 원본 SHA는 보존한 자료의 식별 표식이다. 독자가 없는 원본을 재계산하거나 원래 입력의 바이트 일치를 증명할 수 있다는 뜻이 아니다. cohort 간 call_id 중복0은 원본 장부의 별도 읽기 전용 대조 결과다.
- 연속 인용 검사는 게시한 질문/합성 답변의 문자열 범위만 확인한다. 원문 코드가 의미 판단을 뒷받침하는지는 공개 commit/파일/줄과 사람이 대조해야 한다. 전체 문맥을 생략한 사례의 의미 판정을 검사기가 새로 증명하지 않는다.
- L의12개는 같은 Mastodon 문맥의 노출된 개발 후보다. 최신 정책의 확대 최종12그룹은 미실행이다. 원래 K Q8을 바탕으로 한 n01도 참조를 정렬해 원래 Question 전체의 동일 바이트 재실행이 아니다.
- K9턴의 Director는 `director_v17@calibrated-review`였다. L의 semantic-fit으로 다시9턴을 실행한 기록이 아니며, 지원자 답변은 합성이다. 로그인·WS·브라우저·STT/TTS·리포트 E2E도 아니다. 이 실행에는 실제 Tool 보완·검토 반려·자동 복구가 발생하지 않았다.
- 실제 호출1,254회는 성공한 질문 수·독립 사례 수·전체 계정 사용량이 아니다. Mock·Codex 개발 사용량을 더하지 않으며, cached/reasoning counter도 토큰 총량에 다시 합산하지 않는다. 공급자 실제 청구액은 미확인이다.
- 지연은 당시 공급자·캐시·입력에서 관측한 값이다. 정책만의 인과 효과나 전체 서비스 속도 개선을 확정하지 않는다. 생성 B의196자 장문 한계도 보존한다.
- `publication_integration`은 추출 시점에 아직 실행하지 않은 새 통합 검증을 별도로 표시한다. 이후 새 실행은 이 과거 A~L 수치를 덮어쓰지 않고 별도 기록해야 한다.
