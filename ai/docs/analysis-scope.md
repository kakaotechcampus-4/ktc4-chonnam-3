# W4 분석 대상과 읽기 범위

작성일: 2026-09-16
근거: `spec/ai/features/repository-analysis.md`, `ai/docs/task-04-repo-shallow.md`, `ai/docs/task-05-repo-deep.md`

## 1. 목적과 경계

기본 분석(L1)과 정밀 분석(L2)이 각각 어떤 파일을 읽고 무엇을 읽지 않는지 고정한다. 읽지 않는 범위가 사실표의 `미확인` 항목과 대응한다.

이 문서는 읽기 범위만 정한다. L1·L2 의 실제 구현은 `ai/docs/task-04-repo-shallow.md` 와 `ai/docs/task-05-repo-deep.md` 가 다룬다.

`L0-a` 는 파일을 읽지 않고 저장소 목록 메타데이터만 보는 lightweight filter 이므로(`spec/ai/features/repository-analysis.md` — "LLM을 호출하지 않는다") 사실표의 `미확인` 항목과 대응하지 않는다. 4단계가 모두 보이도록 표에는 남긴다.

## 2. 분석 수준별 읽기 범위

| 수준 | 읽는다 | 읽지 않는다 |
| --- | --- | --- |
| L0-a | 저장소 목록 메타데이터 — 식별자, 공개·접근 상태, fork/archive 여부, 크기, 주 언어, 활동 | 파일 일체. README 도 읽지 않는다 |
| L0-b | README, languages 메타데이터, head SHA, commit 수, 사용자 commit 수 | 파일 내용 일체 |
| L1 | 위 항목 + 의존성 선언 파일, 최상위 디렉터리 목록 | 함수 본문, 설정 값, 테스트 |
| L2 | 고정 SHA 의 **열거된 단일 파일** 원문 | 열거되지 않은 path, 재귀 디렉터리 탐색, 전체 tree, global keyword search |

L2 의 제약은 `ai/docs/task-05-repo-deep.md` 에서 온다.

> directory path 는 AI-L08 상한 승인 전 자동 재귀·전체 tree·global keyword search 로 확장하지 않는다.

따라서 정밀 분석 대상은 "이 디렉터리를 본다" 가 아니라 **"이 파일 N개를 본다"** 로 열거한다.

## 3. 파일 분류 규칙

| 분류 | 예 | 근거 |
| --- | --- | --- |
| L1 입력 | `README.md`, `build.gradle`, `package.json`, `pyproject.toml`, 최상위 디렉터리 목록 | 함수 본문을 읽지 않고도 프로젝트 유형과 확인된 기술을 판단할 수 있다 |
| L2 후보 | 서비스 클래스, 설정 파일, 테스트 파일 — 각각 path 로 열거 | `notable_areas` 의 출발점. 저장소당 1~5개 |
| 대상 아님 | 빌드 산출물, 벤더 디렉터리, 생성 코드, 바이너리 | 원문 확인이 불가능하거나 작성자 판단과 무관 |

### 언어별 읽기 한계

`ai/docs/task-05-repo-deep.md` 가 "지원 기능이 확인되지 않은 언어 source 에서 실행 동작이나 아키텍처를 추론하지 않는다" 를 요구한다. 저장소 3개의 언어가 Java·TypeScript 2종이므로(4절 참고) 이 2종에 한해 실제 L2 후보 파일을 읽고 어디까지 읽을 수 있다고 볼지를 적는다. Python 행은 Python 저장소가 추가될 때 실제 원문을 읽고 채운다.

| 언어 | 읽을 수 있다고 보는 것 | 추론하지 않는 것 |
| --- | --- | --- |
| Java | 클래스·메서드 선언, 어노테이션(`@Service`, `@Transactional`, `@Controller`, `@Configuration`, `@EnableCaching`, `@Bean` 등), import, 필드 타입, `@RequiredArgsConstructor` 같은 Lombok 어노테이션의 존재, 작성자가 남긴 주석에 명시된 의도(예: `AuthService.reissue()` 의 `REQUIRES_NEW` 사용 이유, `application.yml` 의 `transactional-lock: false` 설정 이유) | `@Transactional(REQUIRES_NEW)` 전파가 실제로 별도 커밋을 보장하는지, 동시 요청에서 낙관적 락 충돌·유니크 제약 위반이 주석이 설명한 대로 재현되는지 같은 런타임 동작. Lombok 이 실제로 생성하는 생성자 바이트코드, Spring AOP 프록시의 실제 적용 방식. JPA dirty checking·`default_batch_fetch_size` 같은 설정값이 실행 시 실제로 적용되는 결과 |
| TypeScript | `export` 선언, 타입·인터페이스 정의(`MissionList`, `PostType` 등), import 경로, `"use client"` 지시어의 존재, `useQuery` 같은 훅 호출과 그 인자, JSX 컴포넌트 구성. 함수 본문에서 `error` 가 실제로 체크·반환되는지 여부(예: `createPost`/`createMission` 은 `if (error) return error`로 반환하지만, `updateMission` 은 `error` 를 구조분해했을 뿐 체크·반환 없이 버린다) | `supabase.from(...)` 호출이 실제로 반환하는 런타임 데이터가 타입 선언과 일치하는지(DB 스키마 확인 불가). `createPost`/`createMission` 이 반환한 에러 값을 호출부가 실제로 소비하는지, `updateMission` 이 버리는 에러가 운영 환경에서 조용한 실패로 이어지는지. `useQuery` 의 `cacheTime` 옵션이 실제 캐시 무효화에 미치는 영향, 빌드 후 번들 구조, 타입 소거 이후 런타임 동작 |
| Python | (Python 저장소 추가 시 채운다) | (Python 저장소 추가 시 채운다) |

## 4. 샘플 저장소

이 절의 목록과 L2 후보 path 를 근거로 `ai/evals/expectations/fact-table.md` 의 레코드가 작성되었으나, 그 사람 전수 검수는 아직 미완료다 — 해당 문서의 "사람 전수 검수 — 미완료" 절 참고.

| ID | 저장소 | 언어 | 파일 수 | 고정 SHA | source group |
| --- | --- | --- | --- | --- | --- |
| R1 | JEJUGILMOA/JEJUGILMOA-BE | Java / Spring Boot (Gradle) | 538 | `e04d093f6d18b5cf9794331e9ff56ef100ffd2a3` | `sg-r1` |
| R2 | Savers-Save-Earth/Savers | TypeScript / Next.js | 201 | `89b52b8e78520114c426863e054e7e4169e03905` | `sg-r2` |
| R3 | spring-projects/spring-petclinic | Java / Spring Boot (Maven) | 132 | `818c4136ea971c21674525f9053de0d9c7ad8cfe` | `sg-r3` |

### L2 후보 path

최상위 디렉터리 목록과 의존성 선언 파일만 보고 지목했다. 재귀 탐색을 하지 않았다. 각 path 는 고정 SHA 에서 존재를 확인했다.

**R1 · JEJUGILMOA-BE**

- `src/main/java/com/example/jejugilmoa/domain/auth/service/AuthService.java`
- `src/main/java/com/example/jejugilmoa/domain/auth/service/AppleAuthService.java`
- `src/main/resources/application.yml`

Gradle 프로젝트의 관례적 구조(`src/main/java/<group>/domain/<name>/service`)를 따랐다. 최상위에 `src` 와 `build.gradle` 이 있으면 이 경로를 예측할 수 있다.

**R2 · Savers**

- `src/api/community/post.ts`
- `src/api/mission/getMission.ts`
- `src/app/community/[postUid]/page.tsx`

Next.js App Router 의 관례적 구조(`src/app/<route>/page.tsx`, `src/api/<domain>/<file>.ts`)를 따랐다. 최상위에 `next.config.js` 와 `src` 가 있으면 이 경로를 예측할 수 있다.

**R3 · spring-petclinic**

- `src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java`
- `src/main/java/org/springframework/samples/petclinic/system/CacheConfiguration.java`
- `src/main/resources/application.properties`

Maven 프로젝트의 관례적 구조(`src/main/java/<group>/<domain>/<Name>Controller.java`)를 따랐다. 최상위에 `pom.xml` 과 `src` 가 있으면 이 경로를 예측할 수 있다.

### 선정 근거

**필수 기준 4항목**

| 검사 | R1 | R2 | R3 |
| --- | --- | --- | --- |
| README 에 목적·기능 설명이 문단 단위로 있음 | 86줄 | 97줄 | 181줄 |
| 의존성 선언 파일이 최상위에 있음 | `build.gradle` | `package.json` | `pom.xml`, `build.gradle` |
| 파일 수십~수백 개 | 538 | 201 | 132 |
| L2 후보 path 를 최상위 구조만 보고 지목 가능 | `domain/*/service` 관례 | App Router 관례 | Maven 레이어 관례 |

**구성 조건**

언어·규모 차이 — R1·R3 은 둘 다 Java 이지만 성격이 갈린다. R1 은 Gradle·도메인 패키지 구조·538 파일, R3 은 Maven·레이어 구조·132 파일로 규모가 4배 차이다. R2 는 TypeScript 로 언어가 다르다.

계획은 세 저장소의 언어가 모두 다르기를 요구했으나 Java 2종으로 진행한다. 언어 다양성의 목적이 L2 의 "지원 언어·parser 미확인 시 추론 금지" 경계를 시험하는 것이므로 Java·TypeScript 2종으로도 그 경계를 세울 수 있다. 언어별 읽기 한계 표는 2행으로 작성하고 Python 행은 저장소를 추가할 때 채운다.

문서가 얇거나 생성 코드 비중이 높은 저장소 — R1 이 해당한다. 최상위에 `.claude/`, `.agents/`, `AGENTS.md`, `CLAUDE.md` 가 있어 AI 에이전트를 사용한 개발 흔적이 있다. Java 파일 430개 중 어느 것이 수작성인지 판별할 단서가 파일 자체에는 없으므로, "읽었으나 작성 방식을 판단할 수 없다"는 확인 실패 레코드를 만들기에 적합하다.

알려진 정도 — R3 은 Spring 공식 샘플 저장소로 널리 알려져 있다. 계획은 덜 알려진 저장소를 권고했으나 그대로 사용한다. 오염 가능성이 높은 저장소가 하나 있으면 Task 7 학습 데이터 오염 검사의 양성 대조군이 된다. 세 저장소가 모두 "오염 아님"으로 나오면 검사가 무력한 것인지 저장소가 깨끗한 것인지 구분할 수 없다.

R3 의 L2 사실 2개가 모두 오염으로 판정되면 계획의 "한 저장소의 L2 사실 2개가 모두 오염이면 교체를 검토한다" 경로를 따른다. 그 결정은 W12 에서 한다.

## 5. 재현 절차

```bash
git clone https://github.com/<owner>/<repo>.git
git -C <repo> checkout <고정 SHA>
```

고정 SHA 로 checkout 해야 사실표의 줄 번호가 맞는다. 기본 브랜치 최신을 쓰면 재현되지 않는다.
