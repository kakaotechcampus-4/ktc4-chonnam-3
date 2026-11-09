# 0011 STT 공급자(MLAPI Whisper)와 무음 환각 대응

- 상태: Proposed
- 날짜: 2026-11-02
- 작성: BE (STT 연동 작업)
- 검토자: FE·AI·팀 (검토 대기)
- 관련 PR: 없음 (BE STT 연동 PR에서 연결 예정)
- 관련 결정: [0007](0007-voice-interview-contract.md) 확인 항목 1·3, 이슈 #177·#178

## 맥락

0007은 STT 공급자·모델을 "미정"으로 두었고 `transcriptPartial`을 STT가 스트리밍을 지원할 때만 보내는 선택 메시지로 정했다. BE가 MLAPI Whisper를 실제로 호출해 확인한 결과(2026-11)가 문서의 기대와 달랐고, 무음 입력에 환각 문장이 반환되는 문제가 있었다. 이 기록은 그 사실과 선택을 남긴다. 0007 본문은 바꾸지 않는다.

## 결정

1. **공급자·모델**: MLAPI의 Whisper(`whisper-large-v3`)를 STT로 쓴다. 호출은 `POST {STT_BASE_URL}/v1/audio/transcriptions`(Bearer 인증, multipart `file`·`model`·`language=korean`·`return_timestamps=false`)이다. `language`는 코드(`ko`)가 아니라 이름(`korean`)을 받는다.
2. **응답 형식**: 성공 응답의 전사는 최상위 `text`다. 공급자 문서의 `transcript.text`·`_result.status`는 실제 응답에 없다. 앞뒤 공백은 제거한다.
3. **형식 변환 없음**: webm/opus(`audio/webm;codecs=opus`)가 그대로 전사된다. 서버가 파일 내용으로 형식을 판별하므로 mime·파일명은 결과와 무관하고 ffmpeg 변환은 두지 않는다. Safari mp4/aac는 이번 범위에서 검증하지 않았다.
4. **업로드 방식**: `answerEnd` 뒤 수신한 오디오를 한 번에 올린다. 10초 약 2초, 118초 약 6초가 걸려 충분하다.
5. **`transcriptPartial` 미지원**: MLAPI는 스트리밍 전사를 지원하지 않으므로 BE는 `transcriptPartial`을 보내지 않는다. FE는 최종 `transcript`만으로 동작한다(FE 설계의 `no-partial` 경로).
6. **무음 환각 대응**: 무음·무발화 오디오에도 200과 함께 "감사합니다." 같은 문장이 반환된다. 두 가지를 함께 쓴다.
   - 최소 크기 미만(기본 4096바이트, 약 1초)의 오디오는 STT를 호출하지 않고 `empty_transcript`로 본다.
   - 전사 전체가 설정한 환각 문구(기본 `감사합니다`, 공백·문장부호 무시)와 같고 오디오가 짧을 때(기본 15초 이하, 응답 `usage.seconds`, 없으면 크기로 추정) `empty_transcript`로 본다.
   - 값은 모두 설정으로 바꾼다. 문구 목록은 실측으로 보강하며 필터를 끌 수도 있다.
7. **상한**: 크기·길이 상한과 rate limit은 공급자 문서에서 확인하지 못했다. 기본값(오디오 10MiB, 호출 30초 타임아웃)은 보수적 가정이며 설정으로 조정한다.
8. **오류 표현**: 전사 실패는 WS `error`의 `stt_failed`(`recoverable: true`)다. 빈 전사만 `details.cause="empty_transcript"`를 붙이고 나머지는 `details`를 생략한다. 공급자 응답 원문·상태 코드·키는 어디에도 싣지 않는다.

## 이유

- 대안인 스트리밍 STT는 MLAPI가 지원하지 않는다. 한 번에 올려도 응답 시간이 수 초라 답변 종료 후 대기가 허용 범위다.
- 환각을 빈 문자열 검사만으로는 잡을 수 없다. 길이만으로는 긴 무음을, 문구만으로는 짧은 실제 "감사합니다" 답변 외의 경우를 모두 처리하지 못해 두 조건을 함께 쓴다. 짧은 오디오의 "감사합니다" 단독 답변은 면접 답변으로 가치가 없어 다시 말하게 하는 편이 낫다고 보았다.

## 영향

- BE: `app/integrations/stt/`, 설정 `STT_*`, WS 수신·전사 연결, `error-reasons.md` WS 절.
- FE: `transcriptPartial` 없이 동작해야 한다. 변경 필요 없음(이슈 #177·#178의 작업 나눔을 따른다).
- AI: 영향 없음. 평가에는 최종 전사만 쓰며 환각 필터를 통과한 텍스트만 저장된다.
- 되돌리기: 공급자를 바꾸면 어댑터와 설정만 교체한다. 환각 필터는 설정으로 끈다.
- 미검증: 문구 목록과 15초 기준은 실측 표본이 적다. 운영 오디오로 재측정한다.

## 대체 관계

- 0007의 확인 항목 1(STT 공급자·형식·스트리밍)을 구체화한다. 0007을 대체하지 않는다.
