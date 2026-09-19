/**
 * mock in-memory 저장소의 진입점.
 *
 * 상태는 호출 횟수가 아니라 createdAt 기준 경과 시간에서 파생한다.
 * SSE 스트림과 폴링 응답이 같은 값을 봐야 하기 때문이다.
 * 새로고침하면 초기화되고, seed 레코드는 화면 단독 개발용으로 항상 존재한다.
 */
export * from './config';
export * from './runs';
export * from './interviews';
