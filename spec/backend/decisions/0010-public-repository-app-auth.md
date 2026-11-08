# 공개 저장소 수집의 OAuth App 인증

- 상태: Proposed
- 날짜: 2026-10-30
- 관련 PR: Director 공통 선행 코드, #136
- 검토자: PR 리뷰에서 확인

## 맥락

고정 SHA의 공개 저장소 구조와 파일을 읽는 준비 작업은 익명 GitHub API 한도를 공유한다.
사용자 token을 모든 파일 요청에 전달하면, 사용자가 비공개 저장소 권한도 가진 경우 공개에서
비공개로 바뀐 저장소의 내용을 계속 읽게 될 수 있다. 기존 Evidence 도구의 보호를 유지해야 한다.

## 결정과 이유

BE에 이미 설정하는 OAuth App client ID/secret으로 공개 데이터 전용 Basic 인증을 명시한다.
GitHub가 문서화한 [OAuth App 공개 조회 인증](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#primary-rate-limit-for-oauth-apps)이다.
사용자의 비공개 저장소 권한을 대신 사용하지 않으면서 앱 단위 한도를 사용할 수 있다.

EvidenceReader는 이 인증을 선택적으로 받는다. 준비 수집기는 기존 Settings에서 두 값을 전달한다.
둘 다 없으면 기존 익명 호출을 보존하지만, 일부만 설정됐거나 값이 잘못됐으면 고정 오류로 거절한다.
요청은 정해진 GitHub API 주소에만 만들며 client의 기본 인증·쿠키·redirect를 상속하지 않는다.
응답 오류 본문·자격 증명은 상위 오류나 모델 입력으로 전달하지 않는다.

## 영향과 대체 관계

새로운 환경 변수·사용자 token 권한·공개 API·DB 구조는 추가하지 않는다. 기존 read_files의
사용자 token은 계속 metadata 확인에만 사용한다. 고정 SHA·공개 여부·파일 내용 검증과 요청·바이트·
시간 상한을 유지한다. 기존 Evidence 저장 경계 ADR0005를 보완하며 과거 결정을 덮어쓰지 않는다.

HTTP mock 회귀는 실제 앱 자격 증명의 유효성·GitHub의 현재 잔여 한도·운영 부하를 입증하지 않는다.
실제 검증 결과는 `spec/ai/implementation.md`에서 관리한다.
