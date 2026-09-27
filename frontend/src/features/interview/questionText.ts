/**
 * 5b-v2에서 질문을 텍스트로도 볼지. 준비 화면에서 켜 두고 면접 화면이 이어받는다.
 * 브라우저 저장소라 시크릿 창·차단 설정에서는 읽기·쓰기가 막힐 수 있다.
 */
export const QUESTION_TEXT_KEY = 'devon.showQuestionText';

export function readQuestionText() {
  try {
    return localStorage.getItem(QUESTION_TEXT_KEY) !== 'false';
  } catch {
    return true;
  }
}
