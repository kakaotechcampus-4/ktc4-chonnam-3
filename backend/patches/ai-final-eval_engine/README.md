# 평가 실행·근거 기반 Judge·CLI·CI 후속 변경

이 디렉터리는 미병합 선행 구현에 대한 **이번 신규 수정 구간만** 보존한다.
선행 코드를 다시 복사하지 않으므로 이 PR을 병합하는 것만으로 아래 변경이 실행되지는 않는다.
직접 게시한 새 모듈도 별도 PR의 계약·실행 설정에 의존할 수 있다. 현재 PR은 Draft다.

패치 소유 PR: #214. 아래 표는 이동 후 소유 범위다.

## 적용 순서

1. PR 본문에 연결한 선행 PR과 필요한 계약·구현을 develop에 반영한다.
2. 각 대상 파일을 UTF-8 LF로 정규화한 SHA256이 아래 기준 지문과 같은지 확인한다.
   다르면 파일을 덮어쓰지 말고 최신 코드에 신규 수정의 의도를 병합한다.
3. 저장소 루트에서 해당 `.patch`에 `git apply --check <경로>`를 실행한다.
   모두 검토한 뒤 `git apply <경로>`로 적용하고 최종 지문·호출·모델 입력·저장 경로를 재검증한다.
4. 최종 반영 파일의 정적 검사·회귀·PostgreSQL 통합 검사와 공유 계약 검사를 실행한다.
   이 통합 검증이 통과하기 전에는 전체 기능 완료나 병합 가능 상태로 표시하지 않는다.

patch 안의 앞뒤 문맥은 위치 확인을 위한 것이며 선행 구현 전체를 게시한 것이 아니다.
기존 파일을 보완하는 다른 PR과 파일이 겹치면 적용 순서와 최종 내용을 함께 검토한다.


## 대상과 지문

| 대상 파일 | patch | 적용 전 SHA256 | 적용 후 SHA256 |
| --- | --- | --- | --- |
| `ai/evals/README.md` | [9b342f0b549a-README.md.patch](9b342f0b549a-README.md.patch) | `547181cf63cb4a0a2b3ce51cd42edf3f15d022038889d427c8d844dcc938e124` | `6dda11344ffc3274dad69533f279a13c0209eaa7311a37a208771d625ab1a4fc` |
| `ai/evals/eval_cases.py` | [2eada59a6130-eval_cases.py.patch](2eada59a6130-eval_cases.py.patch) | `2fe15b246e469b6fabc7b44b9d50d5beab925cb5bdbff5daab6e104526133eb7` | `c791ec330316ec2936ae4e12708fc5ae4d0e1ab3bdf6e318d44bfeea77a2febd` |

실행 결과와 남은 작업의 원본 기록은 `spec/ai/implementation.md`다.
PR 본문의 게시본 검증과 과거 로컬 통합 검증을 구분해서 읽는다.
