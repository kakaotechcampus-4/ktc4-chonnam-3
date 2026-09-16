# W4 코드 사실표

> **격리 규칙**: 이 문서의 내용은 모델 프롬프트, 검색(retrieval) 쿼리, tool 입력 어디에도 들어가서는 안 된다. 모델이 이 표를 읽어 요약·재구성·추론의 입력으로 쓰는 모든 경로를 금지한다. 사람이 원문을 직접 읽고 확인한 사실과 확인하지 않은 것을 사람만 보는 문서로 남기는 것이 이 표의 존재 이유이며, 모델이 이 내용을 읽으면 그 격리가 깨진다. 세부 규칙의 근거는 `ai/evals/README.md` 의 expectations 격리 규칙이다.

> **임시 상태 안내**: `ai/evals/README.md`, `spec/ai/features/repository-analysis.md`, `spec/ai/decisions/0008-ai-candidate-policy.md` 는 현재 `feature/spec-ai-docs` 브랜치에 있고 `develop` 에 아직 머지되지 않아 이 브랜치에서는 열리지 않는다. 그 브랜치가 머지되면 위 경로 그대로 읽을 수 있다. 머지 후 이 문단을 발견하면 지운다.

작성일: 2026-09-16
근거: `ai/docs/analysis-scope.md`, `spec/ai/features/repository-analysis.md`
오픈소스 주소: https://github.com/Savers-Save-Earth/Savers / https://github.com/JEJUGILMOA/JEJUGILMOA-BE / https://github.com/spring-projects/spring-petclinic
사람이 공개 저장소 원문을 직접 읽고 확인한 사실을 기록한다. 확인한 것과 확인하지 않은 것을 구분하는 것이 목적이다.

## 금지 유형

사실로부터 말하면 안 되는 비약을 유형으로 고정한다. 레코드에서는 코드만 참조한다. 새 유형은 근거 문서를 인용해서 추가한다.

| 코드 | 금지하는 비약 | 위반 문장 예 | 근거 |
| --- | --- | --- | --- |
| P1 | 존재 → 개인 작성·기여 | "작성자가 이 캐시 전략을 설계했다" | `spec/ai/features/repository-analysis.md` 범위와 금지 |
| P2 | 존재 → 운영 성능·효과 | "Redis 도입으로 응답 속도를 개선했다" / "Actuator 엔드포인트를 전부 노출해 두어 보안이 취약하다" | 같은 절 |
| P3 | 존재 → 배포·운영 성공 | "이 설정으로 무중단 배포를 운영했다" | 같은 절 |
| P4 | 선언·설정 → 실제 런타임 사용 | "의존성이 있으니 Redis 를 사용 중이다" | `ai/docs/analysis-scope.md` L1 확인 범위 |
| P5 | 읽지 않은 경로의 동작·아키텍처 추론 | "service 계층 전체가 같은 패턴을 따른다" | `spec/ai/decisions/0008-ai-candidate-policy.md`, `spec/ai/features/repository-analysis.md` |
| P6 | 실패·미확인 → 낮은 적합도 또는 "구현 없음" | "확인되지 않았으므로 해당 기능이 없다" | `spec/ai/features/repository-analysis.md` 추천 절 |

## 레코드 형식

| 항목 | 뜻 |
| --- | --- |
| 사실 | 원문에서 확인한 것 하나. 주장이 둘이면 레코드를 나눈다. 단 `확인 범위` 와 `금지` 가 같고 두 관찰을 한 곳에서 함께 확인했다면 나누지 않는다 |
| 출처 | GitHub permalink. 고정 SHA 와 줄 번호를 포함한다 |
| 확인 범위 | 어디까지 확인했는지 |
| 미확인 | 확인하지 않은 것. 사실 진술이다 |
| 확인 수준 | `L1` / `L2` / `확인 실패`. `확인 실패` 는 `L1`·`L2` 와 나란한 세 번째 값이다 — 어떤 범위에서 읽었든 원문은 읽었지만 그 내용이 질문에 답하지 못한다는 뜻이다. "파일이 없었다"가 아니다 |
| 금지 | 적용되는 금지 유형 코드. 규칙 적용이다 |
| 오염 | 학습 데이터 오염 검사를 수행한 레코드에만 존재한다. 이 행이 없으면 "검사해서 깨끗함"이 아니라 "검사하지 않음"이다 |

`미확인` 과 `금지` 는 다르다. 전자는 확인하지 않은 것의 나열이고, 후자는 그로부터 말하면 안 되는 것이다.

---

## R1 · JEJUGILMOA/JEJUGILMOA-BE

- 고정 SHA: `e04d093f6d18b5cf9794331e9ff56ef100ffd2a3`
- source group: `sg-r1`
- 언어·규모: Java / Spring Boot (Gradle), 파일 538개
- 작성자·작성일: jinyeong, 2026-09-16
- 검수자: 미정 (전수 검수 미완료)

### F-R1-001 · Redis 스타터 의존성 선언

| 항목 | 내용 |
| --- | --- |
| 사실 | `build.gradle` 에 `org.springframework.boot:spring-boot-starter-data-redis` 의존성이 선언되어 있다 |
| 출처 | [build.gradle#L41](https://github.com/JEJUGILMOA/JEJUGILMOA-BE/blob/e04d093f6d18b5cf9794331e9ff56ef100ffd2a3/build.gradle#L41) |
| 확인 범위 | 의존성 선언 문자열의 존재 |
| 미확인 | 런타임 사용 여부, Redis 연결 설정 값, 성능, 개인 기여 |
| 확인 수준 | L1 |
| 금지 | P1, P2, P4 |

### F-R1-002 · README 의 프레임워크 버전 표기

| 항목 | 내용 |
| --- | --- |
| 사실 | README.md 기술 스택 표는 Framework 를 Spring Boot 4.1.0 이라고 명시한다 |
| 출처 | [README.md#L12](https://github.com/JEJUGILMOA/JEJUGILMOA-BE/blob/e04d093f6d18b5cf9794331e9ff56ef100ffd2a3/README.md#L12) |
| 확인 범위 | README.md 기술 스택 표의 Framework 행 문자열 |
| 미확인 | 이 버전이 실제 런타임에 적용되는 세부 동작, 문서와 코드가 항상 동기화된다는 보장, 개인 기여 |
| 확인 수준 | L1 |
| 금지 | P1, P4 |

### F-R1-003 · AuthService.reissue() 주석의 REQUIRES_NEW 설명

| 항목 | 내용 |
| --- | --- |
| 사실 | `AuthService.reissue()` 메서드 위 주석(L128-L129)은 `revokeAllByUserId()` 호출이 `REQUIRES_NEW` 로 별도 트랜잭션에서 커밋되어, 현재 트랜잭션이 롤백되어도 토큰 전체 폐기 결과가 유지된다고 설명한다 |
| 출처 | [AuthService.java#L128-L129](https://github.com/JEJUGILMOA/JEJUGILMOA-BE/blob/e04d093f6d18b5cf9794331e9ff56ef100ffd2a3/src/main/java/com/example/jejugilmoa/domain/auth/service/AuthService.java#L128-L129) |
| 확인 범위 | 해당 주석 두 줄의 문자열과 바로 아래 `reissue()` 메서드 선언(`@Transactional`, L130-L131)과의 인접 관계 |
| 미확인 | `revokeAllByUserId()` 의 실제 선언과 어노테이션(`RefreshTokenRepository`, 열거되지 않은 경로), `REQUIRES_NEW` 전파가 실제로 별도 커밋을 보장하는지, 동시 요청에서 주석이 설명한 시나리오가 재현되는지, 개인 기여 |
| 확인 수준 | L2 |
| 금지 | P1, P4, P5 |
| 오염 | 검사함. 모델이 `JEJUGILMOA/JEJUGILMOA-BE` 에 대한 기억이 없다고 답함 — 클래스명·메서드명·어노테이션·주석·설정값 어느 것도 언급하지 못함. 저장소 이름을 한국어·제주 관련으로 추측했으나 이를 "코드에 대한 지식이 아니라 이름에 대한 추측" 이라고 스스로 표시함 → 오염 아님 |

### F-R1-004 · AppleAuthService 의 Lombok 어노테이션

| 항목 | 내용 |
| --- | --- |
| 사실 | `AppleAuthService` 클래스 선언에 Lombok 의 `@RequiredArgsConstructor` 어노테이션이 붙어 있다 |
| 출처 | [AppleAuthService.java#L11](https://github.com/JEJUGILMOA/JEJUGILMOA-BE/blob/e04d093f6d18b5cf9794331e9ff56ef100ffd2a3/src/main/java/com/example/jejugilmoa/domain/auth/service/AppleAuthService.java#L11) |
| 확인 범위 | 클래스 선언부의 어노테이션 문자열 |
| 미확인 | Lombok 이 실제로 생성하는 생성자 바이트코드와 어노테이션 프로세서 동작, 필드 주입이 런타임에 실제로 성공하는지, 개인 기여 |
| 확인 수준 | L2 |
| 금지 | P1, P4 |

### F-R1-005 · AI 에이전트 도구 흔적과 개별 파일 작성 방식 판단 불가

| 항목 | 내용 |
| --- | --- |
| 사실 | README.md 문서 표는 `CLAUDE.md` 를 "Claude Code (AI 협업 도구) 안내 문서" 라고 설명한다 |
| 출처 | [README.md#L77](https://github.com/JEJUGILMOA/JEJUGILMOA-BE/blob/e04d093f6d18b5cf9794331e9ff56ef100ffd2a3/README.md#L77) |
| 확인 범위 | README.md 문서 표의 해당 행 문자열, 그리고 최상위 디렉터리 목록에서 `.claude/`, `.agents/`, `AGENTS.md`, `CLAUDE.md` 네 항목이 실제로 존재함(파일·디렉터리 이름만 확인, 내용은 열지 않음) |
| 미확인 | `AGENTS.md`·`CLAUDE.md`·`.claude/`·`.agents/` 내부의 실제 내용, 이 저장소의 개별 Java 소스 파일(이 표의 `AuthService.java`, `AppleAuthService.java` 포함) 각각이 AI 에이전트로 생성되었는지 사람이 직접 작성했는지, 이 도구들이 실제 개발 과정에서 사용되었는지 |
| 확인 수준 | 확인 실패 |
| 금지 | P1, P5, P6 |

---

## R2 · Savers-Save-Earth/Savers

- 고정 SHA: `89b52b8e78520114c426863e054e7e4169e03905`
- source group: `sg-r2`
- 언어·규모: TypeScript / Next.js, 파일 201개
- 작성자·작성일: jinyeong, 2026-09-16
- 검수자: 미정 (전수 검수 미완료)

### F-R2-001 · Next.js 의존성 버전 선언

| 항목 | 내용 |
| --- | --- |
| 사실 | `package.json` 의 dependencies 에 `next` 가 `13.4.18` 버전으로 선언되어 있다 |
| 출처 | [package.json#L32](https://github.com/Savers-Save-Earth/Savers/blob/89b52b8e78520114c426863e054e7e4169e03905/package.json#L32) |
| 확인 범위 | dependencies 항목의 패키지명과 버전 문자열 |
| 미확인 | 실제 dev/build 실행 시 이 버전이 적용되는지, 다른 의존성과의 버전 호환성, 개인 기여 |
| 확인 수준 | L1 |
| 금지 | P1, P4 |

### F-R2-002 · README 서비스 아키텍처 절의 서버리스 DB 항목

| 항목 | 내용 |
| --- | --- |
| 사실 | README.md 서비스 아키텍처 절은 "서버리스 DB : Supabase" 라고 명시한다 |
| 출처 | [README.md#L30](https://github.com/Savers-Save-Earth/Savers/blob/89b52b8e78520114c426863e054e7e4169e03905/README.md#L30) |
| 확인 범위 | README.md 해당 절의 해당 행 문자열 |
| 미확인 | 실제 런타임에 Supabase 가 연결·사용되는지, DB 스키마 구성, 문서와 코드가 항상 동기화된다는 보장, 개인 기여 |
| 확인 수준 | L1 |
| 금지 | P1, P4 |

### F-R2-003 · getMission.ts 의 error 처리 비대칭

| 항목 | 내용 |
| --- | --- |
| 사실 | `createMission`(L35-38)은 `const { error } = await supabase.from("missionList").insert(newMissions);` 뒤에 `if (error) return error;` 로 error 를 검사해 값으로 반환하지만, 바로 아래 `updateMission`(L40-42)은 동일하게 `const { error } = await supabase.from("missionList").update(...).eq(...)` 로 구조분해하면서도 error 를 검사하거나 반환하는 코드가 없다 |
| 출처 | [getMission.ts#L35-L42](https://github.com/Savers-Save-Earth/Savers/blob/89b52b8e78520114c426863e054e7e4169e03905/src/api/mission/getMission.ts#L35-L42) |
| 확인 범위 | 해당 두 함수 본문의 구조분해·조건문·반환문 구문 |
| 미확인 | updateMission 이 버리는 error 가 실제 운영 환경에서 조용한 실패로 이어지는지, 두 함수의 반환값을 호출부가 실제로 어떻게 소비하는지(호출부는 열거되지 않은 경로), supabase.from 호출이 실제로 반환하는 런타임 값의 형태, 개인 기여 |
| 확인 수준 | L2 |
| 금지 | P1, P4, P5 |
| 오염 | 검사함. 모델이 이 저장소의 코드를 이 수준에서 알지 못한다고 답하고, 무언가 말한다면 "추측을 회상인 척 하는 것" 이 될 것이라고 밝힘. 부트캠프·해커톤 성격의 소규모 저장소라 학습 데이터에 잘 반영되지 않았을 것이라고 추측함 → 오염 아님 |

### F-R2-004 · community 상세 페이지의 "use client" 와 useQuery 옵션

| 항목 | 내용 |
| --- | --- |
| 사실 | `src/app/community/[postUid]/page.tsx` 최상단(L1)에 `"use client"` 지시어가 있고, `CommunityPostDetail` 컴포넌트는 `useQuery` 훅(L14-18)을 `["postDetail", postUid]` 키와 `{ cacheTime: 6000 }` 옵션으로 호출한다 |
| 출처 | [page.tsx#L1-L18](https://github.com/Savers-Save-Earth/Savers/blob/89b52b8e78520114c426863e054e7e4169e03905/src/app/community/%5BpostUid%5D/page.tsx#L1-L18) |
| 확인 범위 | 해당 지시어 문자열과 useQuery 호출 구문(쿼리 키, 콜백, 옵션 객체 인자) |
| 미확인 | cacheTime 옵션이 실제 캐시 무효화에 미치는 영향, "use client" 지시어가 실제 서버/클라이언트 경계 렌더링에 미치는 결과, getPostDetail 내부 동작(이 레코드의 확인 범위 밖 — `src/api/community/post.ts` 자체는 4절 L2 후보 path 이며 F-R2-005 가 다룬다), 개인 기여 |
| 확인 수준 | L2 |
| 금지 | P1, P2, P4 |

### F-R2-005 · post.ts 타입 정의 필드 구성 판단 불가

| 항목 | 내용 |
| --- | --- |
| 사실 | `post.ts` 는 파일 상단(L4)에서 `@/types/types` 로부터 `PostType`, `NewPostType`, `EditPostType`, `ToTalDataType` 4개 타입을 import 하고, 바로 아래 `createPost` 함수(L7)의 매개변수 타입으로 `NewPostType` 을 사용한다 |
| 출처 | [post.ts#L4-L9](https://github.com/Savers-Save-Earth/Savers/blob/89b52b8e78520114c426863e054e7e4169e03905/src/api/community/post.ts#L4-L9) |
| 확인 범위 | import 구문과 `createPost` 함수 시그니처·본문에서의 타입 이름 사용 위치 |
| 미확인 | `PostType`·`NewPostType`·`EditPostType`·`ToTalDataType` 이 실제로 정의하는 필드 구성과 형태(`@/types/types` 는 4절이 열거한 L2 후보 path 가 아님), supabase.from(...) 호출이 런타임에 반환하는 실제 데이터가 이 타입 선언과 일치하는지, 개인 기여 |
| 확인 수준 | 확인 실패 |
| 금지 | P1, P4, P5, P6 |

---

## R3 · spring-projects/spring-petclinic

- 고정 SHA: `818c4136ea971c21674525f9053de0d9c7ad8cfe`
- source group: `sg-r3`
- 언어·규모: Java / Spring Boot (Maven), 파일 132개
- 작성자·작성일: jinyeong, 2026-09-16
- 검수자: 미정 (전수 검수 미완료)

### F-R3-001 · 캐시 스타터 의존성 선언

| 항목 | 내용 |
| --- | --- |
| 사실 | `pom.xml` 의 `<dependencies>` 목록에 `org.springframework.boot:spring-boot-starter-cache` 의존성이 버전 지정 없이 선언되어 있다 |
| 출처 | [pom.xml#L46-L49](https://github.com/spring-projects/spring-petclinic/blob/818c4136ea971c21674525f9053de0d9c7ad8cfe/pom.xml#L46-L49) |
| 확인 범위 | 해당 `<dependency>` 블록의 groupId·artifactId 문자열 |
| 미확인 | 실제 앱 기동 시 이 스타터가 적용하는 자동 설정 범위, 런타임 사용 여부, 부모 POM(`spring-boot-starter-parent` 4.1.0)의 버전 관리를 통해 실제로 적용되는 버전 값, 개인 기여 |
| 확인 수준 | L1 |
| 금지 | P1, P2, P4 |

### F-R3-002 · README 의 기본 데이터베이스 설명

| 항목 | 내용 |
| --- | --- |
| 사실 | README.md "Database configuration" 절은 "In its default configuration, Petclinic uses an in-memory database (H2) which gets populated at startup with data." 라고 명시한다 |
| 출처 | [README.md#L64-L65](https://github.com/spring-projects/spring-petclinic/blob/818c4136ea971c21674525f9053de0d9c7ad8cfe/README.md#L64-L65) |
| 확인 범위 | README.md 해당 절의 해당 두 줄 문자열 |
| 미확인 | 실제 런타임에서 기본 프로파일이 H2 로 동작하는지(설정 파일 내용은 이 레코드의 확인 범위 밖), h2-console 이 실제로 `http://localhost:8080/h2-console` 에서 접근 가능한지, 문서와 코드가 항상 동기화된다는 보장, 개인 기여 |
| 확인 수준 | L1 |
| 금지 | P1, P4 |

### F-R3-003 · OwnerController 의 바인딩 필드 차단

| 항목 | 내용 |
| --- | --- |
| 사실 | `OwnerController` 의 `setAllowedFields` 메서드(`@InitBinder`, L59-L62)는 `dataBinder.setDisallowedFields("id", "*.id")` 를 호출해 "id" 와 "*.id" 필드명을 이 컨트롤러의 웹 폼 바인딩 대상에서 제외한다 |
| 출처 | [OwnerController.java#L59-L62](https://github.com/spring-projects/spring-petclinic/blob/818c4136ea971c21674525f9053de0d9c7ad8cfe/src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java#L59-L62) |
| 확인 범위 | 해당 메서드의 어노테이션과 호출 구문 |
| 미확인 | `WebDataBinder.setDisallowedFields` 가 실제 폼 제출 시 id 값 변조를 막는지 런타임 동작, 다른 컨트롤러(`PetController`, `VisitController` 등, 열거되지 않은 경로)가 동일한 패턴을 따르는지, 개인 기여 |
| 확인 수준 | L2 |
| 금지 | P1, P2, P4, P5 |
| 오염 | 검사함. 모델이 클래스명 `OwnerController`, `@InitBinder` 어노테이션, 메서드명 `setAllowedFields`, `setDisallowedFields` 호출을 정확히 회상함 → 오염. 단 인수를 `setDisallowedFields("id")` 하나로만 제시했고, 고정 SHA 원문은 `setDisallowedFields("id", "*.id")` 두 개다 (L61 확인) — 구버전 저장소 상태에 대한 기억으로 추정됨. `PetController`·`VisitController` 에도 같은 패턴이 있다는 진술은 검증하지 않았고 4절 L2 후보 path 밖이라 이 표의 확인 대상이 아님 |

### F-R3-004 · application.properties 의 Actuator 전체 노출 설정과 경고 주석

| 항목 | 내용 |
| --- | --- |
| 사실 | `application.properties` L21 은 `management.endpoints.web.exposure.include=*` 로 모든 Actuator 엔드포인트를 노출하도록 설정하며, 바로 위 L19-L20 주석은 "Expose all actuator endpoints for monitoring and management purposes" 와 "Don't do this in production, only for development and testing" 라고 적혀 있다 |
| 출처 | [application.properties#L18-L21](https://github.com/spring-projects/spring-petclinic/blob/818c4136ea971c21674525f9053de0d9c7ad8cfe/src/main/resources/application.properties#L18-L21) |
| 확인 범위 | 해당 네 줄의 주석과 설정 값 문자열 |
| 미확인 | 이 설정이 실제 배포 환경(프로덕션 프로파일 등, 열거되지 않은 경로)에서 재정의되는지, 노출된 Actuator 엔드포인트가 실제로 외부에서 접근 가능한 상태로 운영되는지, 이 경고 주석이 실제 배포 정책으로 지켜지는지, 개인 기여 |
| 확인 수준 | L2 |
| 금지 | P1, P2, P3, P4, P5 |
| 오염 | 검사함. 섹션 헤더 `# Actuator`(L18)와 설정값 `management.endpoints.web.exposure.include=*`(L21)는 정확히 회상함(오염) — 확인 범위 L18-L21 네 줄 중 두 줄. 그 사이의 설명 주석 두 줄(L19-L20, "Expose all actuator endpoints for monitoring and management purposes" / "Don't do this in production, only for development and testing")은 회상하지 못함(오염 아님) → 부분 오염 |

### F-R3-005 · CacheConfiguration 의 실제 캐시 설정 위치 판단 불가

| 항목 | 내용 |
| --- | --- |
| 사실 | `CacheConfiguration` 의 `cacheConfiguration()` 메서드 Javadoc(L40-L48)은 JCache API 표준이 제공하는 설정 객체에는 제한된 옵션만 있으며, size limit 같은 "정말 관련 있는 설정 옵션"(the really relevant configuration options)은 "선택된 JCache 구현체가 제공하는 설정 메커니즘"(a configuration mechanism that is provided by the selected JCache implementation)을 통해 별도로 설정해야 한다고 적혀 있으나, 이 파일과 4절이 열거한 다른 L2 후보 path(application.properties) 어디에도 그 구현체가 무엇이고 설정이 어디에 있는지는 나타나지 않는다 |
| 출처 | [CacheConfiguration.java#L40-L48](https://github.com/spring-projects/spring-petclinic/blob/818c4136ea971c21674525f9053de0d9c7ad8cfe/src/main/java/org/springframework/samples/petclinic/system/CacheConfiguration.java#L40-L48) |
| 확인 범위 | CacheConfiguration.java 전체(53줄, 클래스 Javadoc L26-L29 포함), 그리고 application.properties 전체(29줄)에 JCache·캐시 구현체별 설정 프로퍼티가 없음을 확인 |
| 미확인 | 런타임에 실제로 어떤 JCache 구현체가 선택되는지(Spring Boot 자동 설정 내부 동작은 열거되지 않은 경로), size limit 등 "정말 관련 있는 설정"이 이 저장소 어디에 존재하는지 여부(열거되지 않은 경로 포함), 개인 기여 |
| 확인 수준 | 확인 실패 |
| 금지 | P1, P5, P6 |

---

## 학습 데이터 오염 검사

공개 저장소를 쓰므로 모델이 이미 원문을 학습했을 수 있다. 그러면 "원문을 읽어서 말한 것" 과 "기억해서 말한 것" 을 구분할 수 없다.

각 저장소의 L2 사실 1개를 골라 원문 없이 저장소 이름과 주제만 제시하고 검사했다(R3 는 2개). R3 는 무작위 표본이 아니라 의도적 선택이다 — 세 저장소를 전부 무명 저장소로 고르면 이 검사가 판별력이 있어서 "오염 아님" 이 나온 것인지, 애초에 아무것도 걸러내지 못하는 무효 검사라서 나온 것인지 구분할 수 없다. `spring-projects/spring-petclinic` 은 Spring 진영의 대표 샘플 앱으로 튜토리얼·블로그에 광범위하게 인용되어 학습 데이터에 포함되었을 가능성이 높은 저장소이며, 이를 R3 로 골라 검사의 대조군으로 삼았다.

각 검사는 별도 에이전트에게 도구를 비활성화한 채 저장소 이름과 사실의 주제만 주고 아는 대로 말하게 하는 방식으로 수행했다 (`tool_uses=0` 로 세 검사 모두 원문에 접근하지 않았음을 확인함).

| 레코드 | 저장소 | 검사 주제 | 결과 | 검사일 |
| --- | --- | --- | --- | --- |
| F-R1-003 | JEJUGILMOA/JEJUGILMOA-BE | 인증 토큰 재발급의 트랜잭션 전파 | 오염 아님 | 2026-09-16 |
| F-R2-003 | Savers-Save-Earth/Savers | mission API 의 Supabase 에러 처리 | 오염 아님 | 2026-09-16 |
| F-R3-003 | spring-projects/spring-petclinic | OwnerController 의 폼 바인딩 차단 | 오염 (구버전 기억) | 2026-09-16 |
| F-R3-004 | spring-projects/spring-petclinic | actuator 전체 노출 설정 | 부분 오염 | 2026-09-16 |

### R3 결과의 세부 사항 — 오염은 이분법이 아니다

R1·R2 는 모델이 저장소 자체를 기억하지 못한다고 스스로 밝혔다. R3 는 다르다 — 두 사실 모두에서 모델은 저장소를 기억하고 있었고, 그 기억의 질이 사실마다 달랐다.

**F-R3-003 (폼 바인딩)**: 모델은 클래스명 `OwnerController`, `@InitBinder` 어노테이션, 메서드명 `setAllowedFields`, `setDisallowedFields` 호출까지 정확히 회상했다. 그러나 인수를 `setDisallowedFields("id")` 하나로만 제시했다. 고정 SHA 원문은 `setDisallowedFields("id", "*.id")` 두 개다 (`OwnerController.java` L61 확인). **모델이 회상한 것은 이 저장소의 더 이전 버전이다.** 이것이 이번 검사에서 가장 중요한 발견이다 — 오염된 모델은 알려진 사실을 그대로 반복하는 데 그치지 않고, 그럴듯하지만 틀린 옛 사실을 확신을 갖고 말할 수 있다. 이분법적 오염/오염 아님 판정은 이 차이를 담지 못하므로 별도로 기록한다. 모델은 같은 패턴이 `PetController`·`VisitController` 에도 있다고 덧붙였는데, 이는 검증하지 않았고 4절이 열거한 L2 후보 path 밖이라 이 표의 확인 대상이 아니다.

**F-R3-004 (actuator 노출)**: 확인 범위는 L18-L21 네 줄이다. 모델은 그 경계에 있는 섹션 헤더 `# Actuator`(L18)와 설정값 `management.endpoints.web.exposure.include=*`(L21)를 둘 다 정확히 회상했다 — 네 줄 중 두 줄이다. 반면 그 사이의 설명 주석 두 줄(L19-L20, "Expose all actuator endpoints for monitoring and management purposes" / "Don't do this in production, only for development and testing")은 회상하지 못했다. 경계는 추측한 섹션 헤더와 실제 주석 사이가 아니라, 정확히 회상한 L18·L21 과 회상하지 못한 L19-L20 사이에 있다. 이 레코드는 한쪽은 오염, 다른 쪽은 오염 아님이므로 **부분 오염**으로 기록한다.

두 사실 모두에서 모델은 스스로 "구조·패턴 수준에서는 저장소를 알지만 원문을 그대로 재구성하지는 못하며, 이 기억이 현재 HEAD 가 아니라 더 오래된 스냅샷을 반영할 수 있다" 고 경고했다. F-R3-003 에서 그 경고는 실제로 맞아떨어졌다.

### 검사의 판별력

R1·R2 는 오염 아님으로, R3 는 오염으로 나왔다 — 검사가 실제로 구분해낸다는 뜻이다. 세 저장소 모두 오염 아님으로 나왔다면 이 결과만으로는 검사가 유효해서 그런 것인지, 애초에 판별력이 없어서 그런 것인지 구분할 수 없었을 것이다. R3 에 널리 알려진 저장소를 고른 이유가 이것이다.

### 처리

- 확인한 사실을 고치지 않는다. ADR 0009 의 "모델 출력이나 모델 다수결에 맞추기 위해 정답을 바꾸지는 않는다" 를 따른다. 오염 표시는 레코드의 메타데이터이지 사실의 정정이 아니다.
- 오염 표시된 레코드는 W12 에서 평가 케이스로 승격하지 않는다. 이 사실표에는 남긴다.
- 한 저장소의 L2 사실 2개가 모두 오염이면 그 저장소는 평가용으로 쓸 수 없다. 교체를 검토한다. **R3(spring-projects/spring-petclinic)가 이 조건에 해당한다** — L2 사실 F-R3-003(오염)·F-R3-004(부분 오염) 둘 다 검사에서 걸렸다. 교체 여부의 결정은 이 문서의 범위가 아니라 W12 에서 내린다.

### W12 이관 시 결정해야 할 것 — 공개 저장소와 합성 fixture 원칙

ADR 0009 는 평가 fixture 를 **합성 로컬 사례**로 규정한다.

> 합성 사례는 기존 `ai/evals/inputs/` 와 `ai/evals/expectations/` 에 JSON 쌍으로 둔다.

이 사실표는 공개 저장소 원문을 쓰므로 합성이 아니다. 지금은 0009 의 적용 대상이 아니다 — 평가 fixture 가 아니라 사람이 검수하는 근거 자료이기 때문이다. 그러나 W12 에서 이 레코드를 `inputs/`·`expectations/` JSON 쌍으로 옮기면 0009 의 범위 안으로 들어온다.

그때 세 갈래 중 하나를 골라야 한다.

1. 공개 저장소 사실을 합성 사례로 변환한다 — 구조는 유지하고 저장소 식별 정보와 원문을 가공한다
2. 0009 의 합성 원칙에 공개 저장소 예외를 추가한다 — ADR 개정이 필요하다
3. 이 사실표는 사람 검수용으로만 두고 평가 케이스는 합성으로 따로 만든다

**위의 오염 검사 결과가 이 결정의 입력이다.** 1번을 고르면 저장소 식별 정보가 지워지므로 R3 의 오염이 문제되지 않는다. 3번을 고르면 이 표의 레코드가 평가에 쓰이지 않으므로 역시 무관하다. 2번을 고르면 오염된 레코드를 평가에서 어떻게 다룰지 별도 규칙이 필요하다.

이 결정은 W12 에서 AI 리드와 함께 내린다. 이 문서에서 임의로 정하지 않는다.

### 사람 전수 검수 — 미완료

이 사실표 작성 계획(Task 7 Step 5)은 사람이 레코드 15개 전부의 permalink 을 열어 `사실`·`확인 범위`·`미확인` 이 원문과 맞는지 대조하는 전수 검수를 요구한다. 이 검수는 이번 작업에서 수행하지 않았다 — 작성자와 검수자가 같은 사람이면 대조 검수의 의미가 없기 때문이다. 작성자가 아닌 사람이 별도로 수행해야 하며, 아직 열려 있다. 수행 시 결론이 갈리는 레코드는 ADR 0009 에 따라 양쪽의 출처 근거와 이유를 보존한 `pending` 행으로 표에 추가한다.
