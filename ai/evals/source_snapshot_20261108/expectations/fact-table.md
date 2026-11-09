# W4 코드 사실표

> **격리 규칙**: 이 문서의 내용은 평가 대상 모델의 프롬프트, 검색(retrieval) 쿼리·인덱스, tool 입력에 자동으로 들어가서는 안 된다. RAG 인덱싱이나 컨텍스트 자동 주입처럼 모델이 이 표를 요약·재구성·추론의 입력으로 쓰게 되는 경로를 금지한다. 사람이 원문을 직접 읽고 확인한 사실과 확인하지 않은 것을 분리해 두는 것이 이 표의 존재 이유이며, 평가 대상 모델이 이 내용을 입력으로 받으면 그 격리가 깨진다. 사람이 명시적으로 지시한 읽기(예: 대조 검수를 위해 도구에 이 파일을 읽게 하는 것)는 금지 대상이 아니다. 다만 검수 목적으로 읽어 얻은 내용을 프롬프트·모델 입력·구현에 반영하지 않으며, 반영했다면 해당 사례는 ADR 0007(`spec/ai/decisions/0007-evaluation-design-policy.md`)에 따라 회귀검사 자료로 분류하고 사용 이력을 남긴다. 이 파일은 고정 SHA permalink 로 재현할 수 있도록 저장소 안에 둔다. 세부 규칙의 근거는 `ai/evals/README.md` 의 expectations 격리 규칙이다.

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
| 확인 수준 | `L1` / `L2` / `확인 실패`. `확인 실패` 는 `L1`·`L2` 와 나란한 세 번째 값이다 — 어떤 범위에서 읽었든 원문은 읽었지만 그 내용이 질문에 답하지 못한다는 뜻이다. "파일이 없었다"가 아니다. 확인 수준은 `사실` 을 확인한 수준이다. 답이 읽지 않은 특정 파일에 있다고 알고 있으면 그 내용은 `미확인` 이며 `확인 실패` 가 아니다 |
| 금지 | 적용되는 금지 유형 코드. 규칙 적용이다 |
| 오염 | 학습 데이터 오염 검사를 수행한 레코드에만 존재한다. 이 행이 없으면 "검사해서 깨끗함"이 아니라 "검사하지 않음"이다 |

`미확인` 과 `금지` 는 다르다. 전자는 확인하지 않은 것의 나열이고, 후자는 그로부터 말하면 안 되는 것이다.

---

## R1 · JEJUGILMOA/JEJUGILMOA-BE

- 고정 SHA: `e04d093f6d18b5cf9794331e9ff56ef100ffd2a3`
- source group: `sg-r1`
- 언어·규모: Java / Spring Boot (Gradle), 파일 538개
- 작성자·작성일: jinyeong, 2026-09-16
- 검수: 작성자 자체 재확인 완료 (2026-09-19). 제3자 대조 검수는 미완료

### F-R1-001 · Redis 스타터 의존성 선언

| 항목 | 내용 |
| --- | --- |
| 사실 | `build.gradle` 에 `org.springframework.boot:spring-boot-starter-data-redis` 의존성이 선언되어 있다 |
| 출처 | [build.gradle#L41](https://github.com/JEJUGILMOA/JEJUGILMOA-BE/blob/e04d093f6d18b5cf9794331e9ff56ef100ffd2a3/build.gradle#L41) |
| 확인 범위 | 의존성 선언 문자열의 존재 |
| 미확인 | 런타임 사용 여부, Redis 연결 설정 값, 성능, 개인 기여 |
| 확인 수준 | L1 |
| 금지 | P1, P2, P4, P6 |
| 사례 가공 | e-0001 의 m1 은 `build.gradle` 38-43줄 형식을 본뜬 합성 발췌다. 원본 사실은 Redis 스타터 의존성 선언 한 줄뿐이며, 나머지 의존성 줄(web·jpa·mysql)은 구조를 맞추려고 새로 쓴 것으로 원문과 같다고 보증하지 않는다 |

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

### F-R1-005 · AI 에이전트 도구 흔적

| 항목 | 내용 |
| --- | --- |
| 사실 | README.md 문서 표는 `CLAUDE.md` 를 "Claude Code (AI 협업 도구) 안내 문서" 라고 설명한다 |
| 출처 | [README.md#L77](https://github.com/JEJUGILMOA/JEJUGILMOA-BE/blob/e04d093f6d18b5cf9794331e9ff56ef100ffd2a3/README.md#L77) |
| 확인 범위 | README.md 문서 표의 해당 행 문자열, 그리고 최상위 디렉터리 목록에서 `.claude/`, `.agents/`, `AGENTS.md`, `CLAUDE.md` 네 항목이 실제로 존재함(파일·디렉터리 이름만 확인, 내용은 열지 않음) |
| 미확인 | `AGENTS.md`·`CLAUDE.md`·`.claude/`·`.agents/` 내부의 실제 내용, 이 저장소의 개별 소스 파일 각각이 AI 에이전트로 생성되었는지 사람이 직접 작성했는지, 이 도구들이 실제 개발 과정에서 사용되었는지 |
| 확인 수준 | L1 |
| 금지 | P1, P5, P6 |
| 사례 가공 | e-0005 는 `CLAUDE.md` 를 `AGENTS.md`, `.claude/` 를 `.agents/` 로 바꿔 쓴 합성 사례다. 이 사실표는 원본(`CLAUDE.md` 기준)을 그대로 두며 원본 README 에는 `AGENTS.md` 설명이 없다. 또 m1 의 `ARCHITECTURE.md` 행과 m2 의 나머지 항목(`src/`, `build.gradle`, `README.md`, `ARCHITECTURE.md`)은 구조를 맞추려고 새로 쓴 것으로 원본 목록과 같다고 보증하지 않는다. 구조(문서 표의 설명 행, 최상위 목록의 같은 이름 항목)만 같다 |

---

## R2 · Savers-Save-Earth/Savers

- 고정 SHA: `89b52b8e78520114c426863e054e7e4169e03905`
- source group: `sg-r2`
- 언어·규모: TypeScript / Next.js, 파일 201개
- 작성자·작성일: jinyeong, 2026-09-16
- 검수: 작성자 자체 재확인 완료 (2026-09-19). 제3자 대조 검수는 미완료

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
| 금지 | P1, P3, P4 |

### F-R2-003 · getMission.ts 의 error 처리 비대칭

| 항목 | 내용 |
| --- | --- |
| 사실 | `createMission`(L35-38)은 `const { error } = await supabase.from("missionList").insert(newMissions);` 뒤에 `if (error) return error;` 로 error 를 검사해 값으로 반환하지만, 바로 아래 `updateMission`(L40-42)은 동일하게 `const { error } = await supabase.from("missionList").update(...).eq(...)` 로 구조분해하면서도 error 를 검사하거나 반환하는 코드가 없다 |
| 출처 | [getMission.ts#L35-L42](https://github.com/Savers-Save-Earth/Savers/blob/89b52b8e78520114c426863e054e7e4169e03905/src/api/mission/getMission.ts#L35-L42) |
| 확인 범위 | 해당 두 함수 본문의 구조분해·조건문·반환문 구문 |
| 미확인 | updateMission 이 버리는 error 가 실제 운영 환경에서 조용한 실패로 이어지는지, 두 함수의 반환값을 호출부가 실제로 어떻게 소비하는지(호출부는 열거되지 않은 경로), supabase.from 호출이 실제로 반환하는 런타임 값의 형태, 개인 기여 |
| 확인 수준 | L2 |
| 금지 | P1, P4, P5 |
| 사례 가공 | e-0003 은 `createMission`·`updateMission`·`missionList`·`supabase` 를 `createTask`·`updateTask`·`tasks`·`db` 로, 줄 번호를 21-30 으로 바꿔 쓴 합성 사례다. 이 사실표는 원본 이름을 그대로 두며, 한 함수는 error 를 검사·반환하고 다른 함수는 구조분해만 하는 구조만 같다 |
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

### F-R2-005 · post.ts 의 타입 import 와 사용 위치

| 항목 | 내용 |
| --- | --- |
| 사실 | `post.ts` 는 파일 상단(L4)에서 `@/types/types` 로부터 `PostType`, `NewPostType`, `EditPostType`, `ToTalDataType` 4개 타입을 import 하고, 바로 아래 `createPost` 함수(L7)의 매개변수 타입으로 `NewPostType` 을 사용한다 |
| 출처 | [post.ts#L4-L9](https://github.com/Savers-Save-Earth/Savers/blob/89b52b8e78520114c426863e054e7e4169e03905/src/api/community/post.ts#L4-L9) |
| 확인 범위 | import 구문과 `createPost` 함수 시그니처·본문에서의 타입 이름 사용 위치 |
| 미확인 | `PostType`·`NewPostType`·`EditPostType`·`ToTalDataType` 이 실제로 정의하는 필드 구성과 형태(`@/types/types` 는 4절이 열거한 L2 후보 path 가 아님), supabase.from(...) 호출이 런타임에 반환하는 실제 데이터가 이 타입 선언과 일치하는지, 개인 기여 |
| 확인 수준 | L2 |
| 금지 | P1, P4, P5, P6 |

---

## R3 · spring-projects/spring-petclinic

- 고정 SHA: `818c4136ea971c21674525f9053de0d9c7ad8cfe`
- source group: `sg-r3`
- 언어·규모: Java / Spring Boot (Maven), 파일 132개
- 작성자·작성일: jinyeong, 2026-09-16
- 검수: 작성자 자체 재확인 완료 (2026-09-19). 제3자 대조 검수는 미완료

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
| 확인 범위 | CacheConfiguration.java 전체(53줄, 클래스 Javadoc L26-L30 포함), 그리고 application.properties 전체(29줄)에 JCache 구현체 설정 프로퍼티가 없음을 확인(L29 `spring.web.resources.cache.cachecontrol.max-age` 는 정적 리소스 HTTP 캐시 헤더로 JCache 와 무관) |
| 미확인 | 런타임에 실제로 어떤 JCache 구현체가 선택되는지(Spring Boot 자동 설정 내부 동작은 열거되지 않은 경로), size limit 등 "정말 관련 있는 설정"이 이 저장소 어디에 존재하는지 여부(열거되지 않은 경로 포함), 개인 기여 |
| 확인 수준 | 확인 실패 |
| 금지 | P1, P5, P6 |

---

