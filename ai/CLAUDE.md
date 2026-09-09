# AI 코딩 AI 작업 지침

루트 CLAUDE.md를 따른다. 모든 spec 경로는 저장소 루트 기준이다.
서비스 명세는 spec/ai/architecture.md, spec/ai/features/, spec/ai/verification.md를 읽는다.
공통 인터페이스는 spec/shared/contracts/README.md와 migration.md를 함께 확인한다.
명세 내용을 이 파일에 복제하지 않고 관련 spec 문서를 갱신한다.

## 실행 환경
작업 디렉터리: backend — 현재 AI 구현 영역
```text
별도 ai 서비스 실행 명령 없음. backend 런타임 상태 확인.
```

## 실행할 검증
```text
backend/tests의 해당 Agent·LLM task 테스트를 확인 후 실행.
모델 기반 평가는 데이터셋·모델 버전·비용·지표를 지정한 뒤 수행.
```
AI 코드는 backend/app 아래에 있으므로 수정 시 backend/CLAUDE.md도 읽는다. 의존성 선언만으로 모델·provider·RAG 저장소 선정을 확정하지 않는다.
미구현·도구 미설치·테스트 없음은 미실행으로 보고한다.

## 산출물 위치
- 기능·설계·결정: spec/ai/ 하위의 해당 문서.
- AI 실행 계획: .claude/scratch/plans/. 인계 메모: .claude/scratch/.
- 코딩 AI 작업 규칙: 이 파일 또는 .claude/skills/.
