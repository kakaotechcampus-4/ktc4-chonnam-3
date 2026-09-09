# FE 코딩 AI 작업 지침

루트 CLAUDE.md를 따른다. 모든 spec 경로는 저장소 루트 기준이다.
서비스 명세는 spec/frontend/architecture.md, spec/frontend/features/, spec/frontend/verification.md를 읽는다.
공통 인터페이스는 spec/shared/contracts/README.md와 migration.md를 함께 확인한다.
명세 내용을 이 파일에 복제하지 않고 관련 spec 문서를 갱신한다.

## 실행 환경
작업 디렉터리: frontend
```text
npm ci
npm run dev
```

## 실행할 검증
```text
npm run lint
npm run build
```
현재 package.json에 test 스크립트는 없다. lint/build를 동작 테스트 통과로 표현하지 않는다.
미구현·도구 미설치·테스트 없음은 미실행으로 보고한다.

## 산출물 위치
- 기능·설계·결정: spec/frontend/ 하위의 해당 문서.
- AI 실행 계획: .claude/scratch/plans/. 인계 메모: .claude/scratch/.
- 코딩 AI 작업 규칙: 이 파일 또는 .claude/skills/.
