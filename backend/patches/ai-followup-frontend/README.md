# 질문 복구 화면 적용 묶음

#219의 최신 음성·텍스트 화면을 먼저 적용한 뒤 화면 차이와 MSW 회귀를 함께 적용합니다. #228 계약·#229 실행이 선행합니다. 공유 hook·형·MSW는 독립 추가로 직접 게시하며, 대기 화면은 같은 UUID를 유지하고 30초 후 결과 재확인과 나가기를 허용합니다. 모델을 새로 실행하지 않습니다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `review-InterviewScreen.tsx.patch` | `frontend/src/features/interview/InterviewScreen.tsx` | `c6bc40b64331ecbcedd02ade686f1690990ef5a58b1f713590abf2c8ea8f6675` | `8aede4aaad4cc788d7f34f5dbd13f67eadc4bb7416a6d38d42104a845d0878cb` | `ef9902aab818fbfc9cbf328bf74ee205ba7fbabf072c891fed96447c43f29690` |
| `review-interview-question-retry.spec.ts.patch` | `frontend/tests/interview-question-retry.spec.ts` | `없음` | `78ac18387d542492124de08dd2496d56b1cb99ea5f07d4fc32f528496b167702` | `479f9e268eb8d2ca46f7ae62718e2becd56df2d834f87b893559cc41ee94ec85` |
