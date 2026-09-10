\# 테이블 확정 과정



\## 1. 계정 관련 테이블



\### Github 연동 API



> (얘는 db에 저장할 녀석이 아니라 참고자료)

> 

\- \*\*(A) 토큰 교환 응답\*\* — `POST https://github.com/login/oauth/access\_token`

&#x20;   

&#x20;   

&#x20;   | 필드 | 조건 |

&#x20;   | --- | --- |

&#x20;   | access\_token | 항상 |

&#x20;   | token\_type | 항상 (bearer 고정) |

&#x20;   | scope | 항상 (공백 구분 문자열) |

&#x20;   | expires\_in | 만료형 토큰일 때만 — 28800초(8시간) |

&#x20;   | refresh\_token | 만료형일 때만 |

&#x20;   | refresh\_token\_expires\_in | 만료형일 때만 — 15897600초(6개월) |

\- \*\*(B) 사용자 프로필\*\* — `GET https://api.github.com/user`

&#x20;   

&#x20;   

&#x20;   | 필드 | 타입 | null |

&#x20;   | --- | --- | --- |

&#x20;   | id | integer(int64) | ✗ |

&#x20;   | node\_id | string | ✗ |

&#x20;   | login | string | ✗ |

&#x20;   | avatar\_url / html\_url | string(uri) | ✗ |

&#x20;   | type | string | ✗ |

&#x20;   | created\_at / updated\_at | date-time | ✗ |

&#x20;   | name | string | ✓ |

&#x20;   | email | string | ✓ |

&#x20;   | company / blog / location / bio | string | ✓ |



\### \[TABLE] users



| \*\*필드\*\* | \*\*타입\*\* | \*\*제약\*\* | \*\*설명\*\* | API 출처 |

| --- | --- | --- | --- | --- |

| id | UUID | PK, default gen\_random\_uuid() |  | devon 자체 |

| display\_name | VARCHAR(50) |  | GitHub name,

없으면 GitHub login | /user에서 `“name”`과`“login”` |

| email | VARCHAR(255) | NULL | Github이 안 줄 수 있음. | /user |

| avatar\_url | TEXT | NULL |  | /user |

| status | VARCHAR(20) | DEFAULT 'active'   | active

suspended(정지)

withdrawn(탈퇴) | devon 자체 status |

| last\_login\_at | TIMESTAMPTZ | NULL

DEFAULT now() |  | devon 에 로그인 한 시간. |

| created\_at | TIMESTAMPTZ | NOT NULL

DEFAULT now() |  | devon 가입 시각 |

| updated\_at | TIMESTAMPTZ | NOT NULL

DEFAULT now() |  | devon이 status를 수정한 시각 추정 용도 |



\### \[TABLE] github\_accounts



| \*\*필드\*\* | \*\*타입\*\* | \*\*제약\*\* | \*\*설명\*\* | API 출처 |

| --- | --- | --- | --- | --- |

| id | UUID | PK |  | 자체 UUID |

| user\_id  | UUID | FK users

UNIQUE |  |  |

| github\_user\_id | BIGINT | NOT NULL

UNIQUE |  | /user의 `id`  |

| github\_node\_id | VARCHAR(50) | NULL | GitHub GraphQL API를 쓸 경우 연결에 활용 | /user의 `node\_id` |

| login | VARCHAR(50) | NOT NULL |  | /user |

|  name | VARCHAR(50) | NULL |  | /user |

| avatar\_url | TEXT | NULL | 아바타 url | /user |

| public\_repo\_count | INT | DEFAULT 0 |  | /user의 `public\_repos` |

| github\_created\_at | TIMESTAMPTZ |  |  | /user의 `created\_at` |

| \*\*access\_token\_encrypted\*\* | \*\*BYTEA\*\* | \*\*NOT NULL\*\* | \*\*암호화 필수!!!

KMS/AES-GCM 암호화\*\* | \*\*/oauth/access\_token의

`access\_token`\*\* |

| token\_type | VARCHAR(20) | DEFAULT 'bearer’ |  | /oauth/access\_token |

| token\_scope | VARCHAR(255) |  | 받은 scope 원문 | /oauth/access\_token의

`scope` |

| token\_expires\_at | TIMESTAMPTZ | NULL | 무기한이면 NULL

github가 주는 건 현재부터 만료까지의 초 단위 시간→ 가공 필요 | /oauth/access\_token의

`expires\_in` |

| refresh\_token\_encrypted | BYTEA | NULL | 만료 대비

이것도 암호화 | /oauth/access\_token의

`refresh\_token` |

| refresh\_token\_expires\_at | TIMESTAMPTZ | NULL | 만료 대비

이것도 가공 필요 | /oauth/access\_token의

`refresh\_token\_expires\_in` |

| updated\_at | TIMESTAMPTZ | NOT NULL

DEFAULT now() | 마지막 동기화 시각 | devon에서 처음 생성할 때 기입. |

| token\_status | VARCHAR(20) | NOT NULL 

DEFAULT 'valid'  | valid / 토큰 상태

expired / 만료

revoked  / Error 401 | 사용자의 토큰이 왜 만료되었는지 빠르게 판단 |



\### \[TABLE] auth\_sessions



클로드가 여러 기기에서 로그인 할 수 있으므로 세션 관리에 대한 테이블도 제안했지만, 본 서비스에서 해당 부분까지 고려하기에는 트레이드오프라고 판단하여 제외함. \[BE 리드 권한]



\## 2. 레파지토리 관련 테이블



\### 분석 정도에 관한 분류



레파지토리를 분석할 때, 각 시기별로 어느정도까지 분석해야하는지 달라서 정리함.



| Layer | 의미 | 대상 | 비용 |

| --- | --- | --- | --- |

| L0-a | 목록 API 응답에 이미 포함

\*\*\[명칭 : 기본 매핑]\*\* | 전체 public 레포 | 100개당 API 1회 |

| L0-b | 레포별 추가 API 호출 필요

\*\*\[명칭 : 추가 매핑]\*\* | 룰 필터 통과분만 | 레포당 API 1\~3회 |

| L1 | shallow LLM (배치)

\*\*\[명칭 : 기본 분석]\*\* | 필터 통과분 | 전체 LLM 1\~2회 |

| L2 | deep LLM

\*\*\[명칭 : 정밀 분석]\*\* | is\_selected=true 3\~5개 | 레포당 LLM 다회 |

| DEVON | 서비스 자체 관리값 | — | 0 |



\#### L0-b에서 말하는 룰 필터



\### 필요성



분석을 진행할 때, 사용자의 레포가 10개보다 많으면 10개 정도만 추려내서 분석하여 레포 추천.



(이후, 사용자가 더 로딩하여 하길 원한다면 지원 예정.)



> 5a-v2 화면에서 사용자가 \*\*"내 레포 더 보기"로 나머지 167개를 볼 수 있어야 함\*\*

> 



\### 제외할 레포 선정하는 경우에 대한 시뮬레이션



```

전체 public repo                              187개

├─ is\_fork = true          제외              -112  ← 강의 자료 클론, 오픈소스 포크

├─ is\_archived = true      제외                -4

├─ size\_kb <= 50           제외               -31  ← README만, 커밋 1\~2개

├─ primary\_language IS NULL 제외               -8  ← 문서/이미지 전용

└─ 남은 후보                                   32개

&#x20;    ORDER BY repo\_pushed\_at DESC LIMIT 10 →  10개  → L0-b + L1 대상

```



\### 제외에 필요한 필드(또는 조건) 부가 설명



| 조건 | 걸러내는 것 | 오검출 위험 |

| --- | --- | --- |

| is\_fork = false | 남의 레포 클론. 면접에서 이거 직접 만드신 거죠?가 성립 안 됨 | 높음 — 포크 후 실제 기여한 오픈소스 컨트리뷰션 |

| is\_archived = false | 본인이 끝났다고 선언한 레포 | 낮음 |

| size\_kb > 50 | 빈 레포, README만 있는 레포, TIL 저장소 | 낮음 (임계값은 실측 후 조정) |

| primary\_language IS NOT NULL | 코드가 없는 레포 | 낮음 |

| LIMIT 20 | 오래된 것 | 있음 — 잘 만든 옛날 프로젝트가 밀림 |



\#### 룰 필터 적용되기 전, 포폴에 먼저 반영하기



\## 포트폴리오 → 레포 추천 반영 설계



\### 문제: 포폴 언급 레포가 룰 필터에 탈락할 수 있어



포폴에 올린 레포가 `is\_fork=true`거나 `size\_kb`가 작으면 룰 필터에서 걸러져. 그런데 \*\*사용자가 대표작이라고 명시한 걸 우리가 빼는 건 말이 안 돼.\*\*



→ M2 후보 선정을 \*\*합집합\*\*으로:



```

M2 후보 = 룰 필터 통과 10개  ∪  포폴 언급 레포

&#x20;                                   ↑ 룰 필터 무조건 우회

```



\### 처리 순서 (M2 안에서)



```

① 포폴 텍스트 추출 → GitHub URL 정규식 파싱

&#x20;    github.com/{owner}/{repo}  → full\_name 추출

② repositories.full\_name 과 매칭 → repository\_id 확보

③ 룰 필터 실행 (10개)

④ ①②결과와 합집합 → 최종 후보

⑤ L0-b + L1 → 매칭 점수

```



②에서 매칭 실패하는 경우가 있어 — 남의 레포, private, 삭제됨, 오타. 이건 \*\*정상 상황\*\*이라 실패 처리하면 안 되고, "포폴에 언급된 3개 중 2개를 찾았습니다" 정도로 알려주면 돼.



\### M3 화면



```

┌──────────────────────────────────────────────┐

│ ☑  devon-backend        📎포트폴리오  ★12   │ ← 배지

│ ☑  payment-service      AI 추천              │

│ ☐  react-dashboard                           │

└──────────────────────────────────────────────┘

```



\---



\### 사용되는 타이밍 정의 (M1\~M5 정리함.)



\- M1. GitHub 연동 직후 · 백그라운드 (UI 없음) \*\*\[L0-a]\*\*

&#x20;   - 연동 되자마자, 전체 레포에 대해 저장 작업 진행.

\- M2. 공고 입력 → 분석 진행 (4-2-v2) \*\*\[L0-b, L1]\*\*

&#x20;   - 상위 10개 선정하여 분석 진행.

&#x20;   - 비용 최적화 (필드 채우기 위한 github api 호출 횟수 줄이기)

&#x20;       

&#x20;       \*\*비용 최적화 하나 짚고 갈게.\*\* `head\_sha`와 `commit\_count`는 따로 부를 필요 없어:

&#x20;       

&#x20;       ```

&#x20;       GET /repos/{owner}/{repo}/commits?per\_page=1

&#x20;         → 응답 body\[0].sha          = head\_sha

&#x20;         → Link 헤더 rel="last"의 page=N = commit\_count

&#x20;       ```

&#x20;       

&#x20;       `user\_commit\_count` : `\&author={login}` 붙여서 같은 방식으로 1회.

&#x20;       

&#x20;       \*\*레포당 4회\*\* (languages, readme, commits, commits?author) → 10개 = 4\*\*0회\*\*.

&#x20;       

\- M3. 레포 확정 화면 (5a-v2) — 필드가 실제로 화면에 나오는 유일한 지점

&#x20;   - 사용자가 어떤 레포를 선택할 지 정보를 보여줌.

&#x20;   

&#x20;   ```

&#x20;   ┌───────────────────────────────────────────────┐

&#x20;   │ ☑  devon-backend                    ★12  ⑂3 │ ← name / stars / forks

&#x20;   │    Spring Boot 기반 면접 시뮬레이터 API 서버    │ ← description

&#x20;   │    ▓▓▓▓▓▓▓░░ Java 68% · TS 21% · SQL 11%      │ ← languages ★

&#x20;   │    #spring-boot #redis #jwt                   │ ← topics

&#x20;   │    3개월 전 · 커밋 142개 (내 커밋 138)          │ ← repo\_pushed\_at / commit\_count

&#x20;   │    💡 공고의 Redis 캐싱 경험과 직접 연관        │ ← repo\_match\_scores.reason

&#x20;   │    ↗ github.com/devon/devon-backend          │ ← full\_name 조립

&#x20;   └───────────────────────────────────────────────┘

&#x20;                             \[ 내 레포 더 보기 (167) ]  ← 룰 필터 탈락분

&#x20;   ```

&#x20;   

\- M4. 면접 진행 중  \*\*\[L2]\*\*



\### \[TABLE] repositories - `★ 중요한 필드 >\_-`



| 필드 | 타입 | 제약 | 설명 | Layer | API 출처 | 사용되는 순간 |

| --- | --- | --- | --- | --- | --- | --- |

| id | UUID | PK

default gen\_random\_uuid() |  | DEVON | 자체 | 쓰기 : M1

&#x20;|

| github\_account\_id | UUID | FK github\_accounts

NOT NULL |  | DEVON | 자체 |  |

| github\_repo\_id | BIGINT | NOT NULL | GitHub 원본 ID. 레포명 변경 대응 | L0-a | `GET /user/repos`

id | 쓰기 : M1 |

| full\_name | VARCHAR(255) | NOT NULL | owner/name | L0-a | `GET /user/repos`

full\_name | 쓰기 : M1

읽기 : M2

읽기 : M3

활용 : M4 |

| name | VARCHAR(100) | NOT NULL |  | L0-a | `GET /user/repos`

name | 쓰기 : M1

읽기 : M3 |

| description | TEXT | NULL |  | L0-a | `GET /user/repos`

description | 쓰기 : M1

읽기 : M3 |

| primary\_language | VARCHAR(50) | NULL | 주 언어 1개 (string | null) | L0-a | `GET /user/repos`

language | 쓰기 : M1

읽기 : M2 |

| topics | TEXT\[] | NULL | ★ L1 보조 입력. 추가 호출 0회 | L0-a | `GET /user/repos`

topics | 쓰기 : M1

읽기 : M2

읽기 : M3 |

| stars | INT | NOT NULL

DEFAULT 0 |  | L0-a | `GET /user/repos`

stargazers\_count | 쓰기 : M1

읽기 : M3 |

| forks | INT | NOT NULL

DEFAULT 0 |  | L0-a | `GET /user/repos`

forks\_count | 쓰기 : M1

읽기 : M3 |

| is\_private | BOOLEAN | NOT NULL

DEFAULT false | OAuth scope에 repo 포함 여부에 따라 값 존재 | L0-a | `GET /user/repos`

private | 쓰기 : M1 |

| is\_fork | BOOLEAN | NOT NULL

DEFAULT false | ★ 포크 제외 — 룰 필터 1순위 | L0-a | `GET /user/repos`

fork | 쓰기 : M1

읽기 : M2 |

| is\_archived | BOOLEAN | NOT NULL

DEFAULT false | ★ 아카이브 제외 | L0-a | `GET /user/repos`

archived | 쓰기 : M1

읽기 : M2 |

| size\_kb | INT | NOT NULL

DEFAULT 0

(필터에서 계산할 때, Null값이면 배제되므로.) | ★ 빈 레포·README-only 판별. 단위 KB (공식 문서에 단위 명시 없음, 실측 기준) | L0-a | `GET /user/repos`

size | 쓰기 : M1

읽기 : M2 |

| default\_branch | VARCHAR(100) | NULL | L0-b 조회 시 기준 브랜치 | L0-a | `GET /user/repos`

default\_branch | 쓰기 : M1

읽기 : M2

활용 : M4 |

| repo\_created\_at | TIMESTAMPTZ | NULL |  | L0-a | `GET /user/repos`

created\_at | 쓰기 : M1 |

| repo\_pushed\_at | TIMESTAMPTZ | NULL | 최신성 판단. ★ pushed\_at에서 개명 (repo\_ 접두사 통일) | L0-a | `GET /user/repos`

pushed\_at | 쓰기 : M1

읽기 : M2

읽기 : M3 |

| languages | JSONB | NULL | {Java:65.2,TypeScript:20.1} — 프로필 언어 그래프 원천 | L0-b | GET /repos/{o}/{r}/languages | 쓰기 : M2

읽기 : M3 |

| readme\_text | TEXT | NULL | base64 디코딩 후 저장. \*\*L1 핵심 입력\*\* | L0-b | GET /repos/{o}/{r}/readme | 쓰기 : M2

읽기 : M2 |

| head\_sha | VARCHAR(40) | NULL | 스냅샷 기준값 + 분석 캐시 무효화 키

`…?per\_page=1` → \*\*body\[0].sha\*\* | L0-b | GET /repos/{o}/{r}/commits?per\_page=1 | 쓰기 : M2

읽기 : M3

활용 : M4 |

| commit\_count | INT | NULL | Link 헤더 `rel="last"`의 page=N | L0-b | commits 페이지네이션 | 쓰기 : M2

읽기 : M3 |

| user\_commit\_count | INT | NULL | 본인 커밋 수 — 기여도 판단. L0-b 중 가장 비쌈

`…?per\_page=1\&author={login}` → Link 헤더 | L0-b | ?author={login} | 쓰기 : M2

읽기 : M3 |

| fetch\_level | VARCHAR(10) | NOT NULL

DEFAULT 'list' | ★ list / detail. 필수 — readme\_text IS NULL이 미조회인지 README 없음인지 구분하는 유일한 수단 | DEVON | 자체 | 쓰기 : M1

(기본 list)

쓰기 : M2

(상위 10개 해당되면 detail) |

| collected\_at | TIMESTAMPTZ | NOT NULL

DEFAULT now() | 목록(L0-a) 수집 시각 | DEVON | 자체 | 쓰기 : M1 |

| detail\_fetched\_at | TIMESTAMPTZ | NULL | 상세(L0-b) 수집 시각 | DEVON | 자체 | 쓰기 : M2 |

| updated\_at | TIMESTAMPTZ | NOT NULL

DEFAULT now() |  | DEVON | 자체 |  |



\### \[TABLE] repo\_analyses



| 필드 | 타입 | 제약 | 설명 | Layer | 사용되는 순간

(요약 표 참고) | 활용 |

| --- | --- | --- | --- | --- | --- | --- |

| id | UUID | PK

default gen\_random\_uuid() |  | DEVON |  |  |

| repository\_id | UUID | FK repositories

NOT NULL |  | DEVON |  |  |

| analysis\_level | VARCHAR(10) | NOT NULL | ★ shallow / deep — 본 개편의 핵심 컬럼

shallow : M2

deep : M4 | DEVON | 쓰기 : M2

쓰기 : M4

&#x20;| 캐시 조회 분기 |

| head\_sha | VARCHAR(40) | NOT NULL | ★ 분석 대상 커밋. 캐시 무효화 키 — 레포에 push가 오면 새 sha → 자동 재분석 | DEVON | 쓰기 : M2 | 캐시 히트 판정 + UNIQUE 성립 |

| analysis\_job\_id | UUID | FK analysis\_jobs

NULL | 어느 회차/배치에서 생성됐는지. 기존 테이블 재사용 | DEVON |  | 어느 회차 산출물인지 추적 |

| project\_types | TEXT\[] | NULL | {web\_backend, api\_server} | L1 | 쓰기 : M2 | 매칭 점수, 프로필 태그 |

| tech\_stack | JSONB | NULL | \[{name:Redis,confidence:0.9,source:docker-compose.yml}].

&#x20;

deep에서 보강

(verified 필드 추가) | L1 → L2 | 쓰기 : M2

쓰기 : M4 | \*\*JD 대조 / 카드 / 질문 주제 / 채점\*\* — 최다 사용 |

| role\_summary | TEXT | NULL | 역할·목적 요약 1\~2문단. 매칭 근거 문구의 원천 | L1 | 쓰기 : M2 | 5a-v2 카드, match reason |

| architecture\_summary | TEXT | NULL | deep 전용. shallow에서는 항상 NULL | L2 |  | Director 첫 질문 컨텍스트 |

| \*\*notable\_areas\*\* | \*\*JSONB\*\* | \*\*NULL\*\* | \*\*★★★ P0. \[{area:인증,path:src/auth,note:...}] — Evidence Tool 호출 대상 선정 입력\*\* | \*\*L2\*\* |  | \*\*Tool 검색 힌트

`{path:"src/main/resources/application.yml", note:"TTL 30분 고정, 산정 근거 없음"}`\*\* |

| status | VARCHAR(20) | NOT NULL

DEFAULT 'succeeded' | ★ succeeded / failed / partial. 배치 shallow에서 일부 레포만 실패하는 경우를 기록 | DEVON |  | 4-3-v2 부분 실패 표시 |

| error\_code | VARCHAR(50) | NULL | ★ llm\_timeout / parse\_failed / input\_too\_large | DEVON |  | 4-3-v2 부분 실패 표시 |

| model | VARCHAR(50) | NOT NULL | 사용 모델 | DEVON |  | Eval 회귀 비교 |

| prompt\_version | VARCHAR(20) | NOT NULL | Eval 회귀 비교용 — 필수 | DEVON |  | Eval 회귀 비교 |

| input\_tokens | INT | NULL | ★ P1. 배치 vs 개별 호출 비용 비교용 | DEVON |  | 배치 vs 개별 비용 실측 |

| output\_tokens | INT | NULL | ★ P1 | DEVON |  | 배치 vs 개별 비용 실측 |

| latency\_ms | INT | NULL | ★ P1. 분석이 오래 걸린다 우려의 실측 근거 | DEVON |  | "분석이 느리다" 우려의 실측 근거 |

| raw\_output | JSONB | NULL | LLM 원문 (디버깅) | DEVON |  | 파싱 실패 디버깅 + L1 입력 보존 |

| analyzed\_at | TIMESTAMPTZ | NOT NULL

DEFAULT now() |  | DEVON |  |  |



\#### repo\_analyses 읽기·쓰기 매트릭스 (자세히)



\### 단계 세분화 (분석 외의 과정도 포함)



| 순간 | 화면 | 일어나는 일 |

| --- | --- | --- |

| M1 | 없음(백그라운드) | GitHub 연동 직후 — L0-a 수집 |

| M2 | 4-2-v2 분석 진행 | 룰 필터 → L0-b → L1 shallow → 매칭 점수 |

| M3 | 5a-v2 레포 확정 | 추천 카드 표시 → 사용자 확정(Human Gate) |

| M4-a | 면접 준비 로딩 | 확정분만 L2 deep |

| M4-b | 면접 진행 | Director 질문 + Evidence Tool 호출 |

| M5 | 홈/프로필 | 확정 레포 기반 프로필 |

| M6 | 리포트 | 채점 → 리포트 생성/조회 |



`W` = 쓰기, `R` = 읽기, `—` = 미사용



| 필드 | M1 | M2 | M3 | M4-a | M4-b | M5 | M6 | 오프라인 |

| --- | --- | --- | --- | --- | --- | --- | --- | --- |

| id | — | W | — | W | — | — | — | — |

| repository\_id | — | W | R | W R | R | R | R | R |

| analysis\_level | — | Wshallow 

R | R | Wdeep

R | R | R | R | R |

| head\_sha | — | W R | — | W R | — | — | — | — |

| analysis\_job\_id | — | W | — | W | — | — | — | R |

| project\_types | — | W R | R | — | — | R | — | R |

| tech\_stack | — | W R | R | W R | R | — | R | R |

| role\_summary | — | W R | R | — | — | R | — | — |

| architecture\_summary | — | — | — | W R | R | — | — | — |

| notable\_areas | — | — | — | W R | R | — | — | — |

| status | — | W R | R | W R | — | — | — | R |

| error\_code | — | W R | R | W R | — | — | — | R |

| model | — | W | — | W | — | — | — | R |

| prompt\_version | — | W R | — | W R | — | — | — | R |

| input\_tokens | — | W | — | W | — | — | — | R |

| output\_tokens | — | W | — | W | — | — | — | R |

| latency\_ms | — | W | — | W | — | — | — | R |

| raw\_output | — | W | — | W | — | — | — | R |

| analyzed\_at | — | W R | R | W R | — | — | — | R |



\#### 필드 읽는 주요 순간



| 필드 | 읽기 목적 |

| --- | --- |

| project\_types | M2 매칭 점수 계산 입력 · M3 카드 유형 배지 · M5 프로필 태그 |

| tech\_stack | M2 JD 요구사항 대조 · M3 카드 스택 표시 · M4-a 질문 주제 선정 · M4-b 꼬리질문 주제 · M6 verified:false 감점 |

| role\_summary | M2 repo\_match\_scores.reason 생성 입력 · M3 카드 설명 문구 · M5 프로필 요약문 |

| architecture\_summary | M4-a 첫 질문 생성 컨텍스트 · M4-b Director 컨텍스트 유지 |

| notable\_areas | M4-a 첫 질문 근거 · M4-b Tool 검색 힌트 |

| status/error\_code | M2 진행률(10개 중 8개) · M3 실패 카드 회색 처리 · 4-3-v2 문구 분기 |

| analyzed\_at | M3 3일 전 분석 표시 · 캐시 TTL 판정(선택) |



\#### 에러(status와 error\_code)에 관한 구체적인 상황(repo 하나와 repo 전체)



\### 층위를 먼저 구분



| 테이블 | 단위 | 예시 |

| --- | --- | --- |

| `analysis\_jobs.error\_code` | \*\*작업 전체\*\* | `no\_public\_repo`, `rate\_limited`, `jd\_parse\_failed` |

| `repo\_analyses.error\_code` | \*\*레포 1개\*\* | 아래 표 |



10개 중 3개가 실패하면 → \*\*job은 `succeeded`, 개별 row 3개가 `failed`.\*\* 이 구분이 없으면 3개 때문에 전체를 실패 처리하게 돼.



\### status 3값



| 값 | 상황 |

| --- | --- |

| `succeeded` | 필수 필드가 다 채워짐 |

| `failed` | 결과 없음. 해당 레포는 매칭 후보에서 제외 |

| `partial` | \*\*배치 때문에 필요한 값.\*\* 예: `project\_types`는 나왔는데 `tech\_stack`이 빈 배열. 카드는 띄우되 매칭 점수는 낮게 |



\### error\_code 상황별



| error\_code | 발생 | 실제 상황 | 화면 | 재시도 |

| --- | --- | --- | --- | --- |

| `llm\_timeout` | M2, M4-a | 배치 응답 타임아웃 | "분석이 지연되고 있습니다" | 자동 1회 |

| `parse\_failed` | M2, M4-a | LLM이 JSON 형식을 안 지킴 | 동일 | 자동 1회 |

| `input\_too\_large` | M2 | README가 수백 KB — 컨텍스트 초과 | 카드에 "정보 부족" | \*\*X\*\* (입력 잘라서 1회) |

| `no\_readme` | M2 | README 없음 → 판단 근거 부족 | 카드 회색 + "정보 부족" | \*\*X\*\* |

| `repo\_unreachable` | M4-a | 확정 후 레포가 private 전환/삭제됨 | "레포에 접근할 수 없습니다" | \*\*X\*\* |

| `token\_invalid` | M2, M4-a | GitHub 토큰 만료/취소 | "GitHub 재연동이 필요합니다" | 재로그인 |



> `token\_invalid`는 앞서 정한 \*\*`github\_accounts.token\_status`와 연동돼야 해.\*\* 여기서 401을 받으면 `token\_status='revoked'`로 UPDATE하고, 다음 요청은 GitHub 호출 전에 차단. 이게 그 컬럼을 넣은 이유가 실제로 쓰이는 지점이야.

> 



\### 읽기 시점



\- \*\*M2\*\*: `COUNT(\*) FILTER (WHERE status='succeeded')` → "20개 중 17개 분석 완료" 진행률

\- \*\*M3\*\*: `failed` 레포는 카드 회색 처리 + `error\_code`별 문구 + \[재시도] 버튼

\- \*\*M4-a\*\*: `repo\_unreachable`이면 그 레포를 빼고 면접 진행 (전체 중단 아님)



\#### 평가 관련 필드(prompt\_version, model, input/output tokens, latency\_ms)



\## model / prompt\_version — 어떤 Eval인가



\### Eval 1 — tech\_stack 정확도 회귀



\*\*골든셋\*\*: 사람이 손으로 라벨링한 레포 20개 (실제 기술 스택 정답지)



```

SELECT prompt\_version, model,

&#x20;      AVG(정답\_일치율) AS accuracy,

&#x20;      COUNT(\*)

FROM repo\_analyses

WHERE repository\_id IN (골든셋) AND analysis\_level='shallow'

GROUP BY prompt\_version, model;

```



→ \*v1.2에서 v1.3으로 프롬프트를 바꿨더니 스택 인식 정확도가 0.78 → 0.85로 올랐나?\*



\### Eval 2 — `verified` 판정 정확도 (L2 전용)



README에는 있는데 코드엔 없는 기술을 실제로 `verified:false`로 잡아냈는가. \*\*거짓 주장 탐지율\*\*이야. 이게 서비스 차별점의 핵심이라 회귀가 나면 안 되는 지표.



\### Eval 3 — 추천 채택률과의 상관 ★ 가장 중요



```

SELECT ra.prompt\_version,

&#x20;      COUNT(\*) FILTER (WHERE sr.was\_ai\_recommended AND sr.is\_selected)::float

&#x20;    / NULLIF(COUNT(\*) FILTER (WHERE sr.was\_ai\_recommended), 0) AS adoption\_rate

FROM session\_repositories sr

JOIN repo\_analyses ra ON ra.repository\_id = sr.repository\_id

GROUP BY ra.prompt\_version;

```



\*\*이게 문서에 이미 있는 보조지표 "GitHub 추천 Repository 채택률"과 직결돼.\*\* 오프라인 골든셋 정확도가 아니라 \*\*실사용자가 AI 추천을 얼마나 받아들였는가\*\*로 프롬프트를 평가하는 거야. Eval 1보다 이게 진짜 지표야.



\### `model`이 왜 따로 필요한가



`prompt\_version`은 그대로 두고 \*\*모델만 바꾸는\*\* 경우가 있어 — 비용 절감으로 Opus → Sonnet 전환 같은 것. 그때 "품질이 얼마나 떨어지나"를 비교하려면 두 축이 분리돼야 해.



> \*\*⚠ 여기서 스키마 문제가 하나 나와\*\*

> 

> 

> 현재 UNIQUE가 `(repository\_id, analysis\_level, head\_sha, prompt\_version)`인데, \*\*같은 레포를 두 모델로 A/B 돌리면 UNIQUE 위반\*\*이야. 모델 비교 실험을 할 거면:

> 

> ```

> UNIQUE (repository\_id, analysis\_level, head\_sha, prompt\_version, model)

> ```

> 

> 로 바꿔야 해. 대신 캐시 조회 쿼리에도 `AND model = $CURRENT\_MODEL`을 넣어야 하고, 모델을 바꾸면 캐시가 전부 무효화돼. \*\*A/B를 안 할 거면 지금 그대로 두는 게 나아.\*\* 1단계에서 모델 비교 실험 계획이 있는지에 달렸어.

> 



\---



\## 배치 vs 개별 비용 실측 — 측정 항목



\### 왜 재나



배치(20개 한 프롬프트)로 가기로 했는데, \*\*그게 정말 이득인지 검증이 안 됐어.\*\* 토큰은 줄지만 품질과 지연은 나빠질 수 있어.



\### 토큰 절감 계산



```

개별 10회 : (프롬프트 오버헤드 400 + 레포 데이터 1,500) × 10 = 19,000 input

배치 1회  :  프롬프트 오버헤드 400 × 1 + 레포 데이터 1,500 × 10 = 15,400 input

&#x20;                                                   절감 3,600 (19%)

```



`input\_tokens` 합계로 실측.



\### 실제로 알고 싶은 4가지



| 지표 | 계산 | 무슨 결정에 쓰이나 |

| --- | --- | --- |

| \*\*토큰 절감률\*\* | `SUM(input\_tokens)` 배치 vs 개별 | 배치 유지 여부 |

| \*\*총 지연\*\* | `latency\_ms` | 배치 1회(15초) vs \*\*개별 20회 병렬(5초)\*\*. 병렬이면 개별이 더 빠를 수 있어 |

| \*\*위치별 품질\*\* | 배치 내 순서별 `tech\_stack` 정확도 | 뒤쪽 레포 품질이 떨어지면(lost in the middle) \*\*배치 크기를 20 → 10으로\*\* |

| \*\*실패 전파\*\* | `status='failed'` 비율 | 배치는 1건 파싱 실패가 20건 전체를 날릴 위험. 개별은 1건만 실패 |



3번(위치별 품질)이 가장 중요한데, \*\*지금 스키마로는 못 재.\*\* 같은 배치 안의 20개 row가 `analyzed\_at`이 전부 같아서 순서를 복원할 수 없어.



> \*\*선택적 추가 (P2):\*\* `batch\_position SMALLINT NULL` — 배치 내 순번(1\~20).

> 

> 

> 배치 크기를 실험으로 정할 계획이 있으면 필요하고, 20개로 고정하고 갈 거면 불필요해.

> 



\### 4번의 실무적 함의



배치의 진짜 위험은 비용이 아니라 \*\*실패 전파\*\*야. LLM이 JSON을 한 군데 깨뜨리면 20개가 통째로 `parse\_failed`가 될 수 있어. 그래서:



\- 배치 응답을 \*\*레포 단위로 부분 파싱\*\*하고, 깨진 것만 `failed` 처리

\- `raw\_output`에 배치 원문 전체를 남겨서, 파싱 로직만 고쳐 \*\*재분석 없이 복구\*\* 가능하게



`raw\_output`을 유지하는 실질적 이유가 이거야 — 단순 디버깅용이 아니라 \*\*LLM 재호출 없이 복구하는 수단\*\*이야.



\#### Unique, Index 설정



```

UNIQUE (repository\_id, analysis\_level, head\_sha, prompt\_version)

INDEX  (repository\_id, analysis\_level, analyzed\_at DESC)

CHECK  (analysis\_level IN ('shallow','deep'))

CHECK  (analysis\_level = 'deep' OR architecture\_summary IS NULL)

```



\### \[TABLE] user\_profile\_summaries



> 홈 대시보드에 나오는 프로필

> 



| 필드 | 타입 | 제약 | 설명 |

| --- | --- | --- | --- |

| id | UUID | PK |  |

| user\_id | UUID | FK users, \*\*UNIQUE\*\* | 1인 1프로필 (누적) |

| based\_repo\_ids | UUID\[] | NOT NULL | 재생성 판정 키.

논리적으로 `repositories.id` 참조. \*\*정렬 저장 필수\*\* |

| based\_repo\_count | INT | NOT NULL DEFAULT 0 | "레포 5개 기반" 문구 |

| language\_distribution | JSONB | NOT NULL DEFAULT '{}' | 확정 레포의 `languages` 합산 |

| project\_type\_tags | TEXT\[] | NULL | `repo\_analyses.project\_types` 합집합 |

| tech\_stack\_top | JSONB | NULL | 빈도 상위 + `verified` 비율 |

| role\_summary | TEXT | NULL | 유일한 LLM 산출물 |

| prompt\_version | VARCHAR | NULL | 요약 관련 프롬프트 변경 시, 사용자 프로필 요약 문구 자동 변경.

1단계에서는 빼고, `based\_repo\_ids` 변경만으로 |

| generated\_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |  |



\## 3. 공고와 JD



\### 실제 공고 URL(사람인) 주고 실측해 본 결과



\### 실측 결과



| 확인 항목 | 결과 |

| --- | --- |

| 봇 차단 | \*\*없음.\*\* 평범한 curl로 HTTP 200 (396KB) |

| 공고 페이지 HTML에 본문 있나 | \*\*없음.\*\* 텍스트 4.4KB가 전부 사이트 네비게이션 메뉴 |

| 본문은 어디서 오나 | `/zf\_user/jobs/relay/view-detail?rec\_idx=...\&rec\_seq=0` |

| 그 엔드포인트를 curl로 되나 | \*\*됨.\*\* 200, 17.7KB. \*\*헤드리스 브라우저 불필요\*\* |

| 본문 형태 | \*\*텍스트 메타 + 이미지 1장\*\* |



`view-detail` 응답 :



```

텍스트 11.7KB → 회사명, 직무 분류, 근무조건 등 "메타데이터"

이미지 1장    → https://www.saraminimage.co.kr/recruit/bbs\_recruit26/42\_simpac\_img\_260831.png

&#x20;             (1.88MB PNG, 로그인 없이 공개 접근 가능)



자격요건 / 담당업무 / 우대사항 키워드 → 텍스트에 0건

```



\### 결론 : 이미지 URL인 경우가 대다수니 이에 맞게 DB 구성



\#### 원티드로 결정한 이유



\### 3사 비교 결과



| 항목 | 사람인 | 잡코리아 | \*\*원티드\*\* |

| --- | --- | --- | --- |

| 페이지 fetch (plain curl) | 200 / 396KB | 200 / 138KB | 200 / 155KB |

| 초기 HTML에 JD 본문 | ❌ 텍스트 4.4KB, 전부 네비게이션 | ❌ 텍스트 1.5KB, JD 키워드 0 | ❌ (SPA) |

| 본문 획득 경로 | ✅ `view-detail` 발견 | ❌ \*\*미발견\*\* (엔드포인트 3종 모두 404) | ✅ \*\*공개 JSON API\*\* |

| 본문 형태 | \*\*이미지 PNG 1.88MB\*\* | 미확인 (이미지 1개) | \*\*구조화된 텍스트\*\* |

| URL → ID 파싱 | `?rec\_idx=` + `rec\_seq` 조립 | `/GI\_Read/{id}` | `/wd/{id}` — 가장 단순 |

| 헤드리스 브라우저 | 불필요 | ? | 불필요 |



잡코리아는 사람인처럼 별도 엔드포인트가 있을 텐데 추측 3개가 다 404였어. 브라우저 Network 탭을 봐야 찾을 수 있고, 찾아도 사람인처럼 이미지일 가능성이 높아.



\### 원티드가 결정적으로 유리한 이유



`https://www.wanted.co.kr/api/chaos/jobs/v1/{id}/details` 응답이 \*\*JD를 항목별로 이미 나눠서\*\* 줘:



```

position          포지션명

intro             703자   회사·팀 소개

main\_tasks       1193자   담당업무

requirements      710자   자격요건

preferred\_points  809자   우대사항

benefits          516자   복지

skill\_tags        기술 태그 (이미 구조화됨)

\+ company, annual\_from/to, employment\_type, location, category\_tag

```



실제 내용도 그대로 나와:



> `"requirements":"\[이런 분과 함께 성장하고 싶습니다]\\n• HRBP 또는 HR유관(채용·평가·보상·조직개발 등) 실무 경력 5\~10년\\n• 채용을 직접 리드해 성사시켜본 경험이 있으신 분..."`

> 



\#### 1차 스프린트와 2차 스프린트 경계 (구현 하기 전 다시 보기)



한 문장으로 정리하면:



> \*\*1차는 "소재 + 체크리스트"(단방향), 2차는 "검증 + 대조"(양방향).\*\*

> 



같은 테이블을 쓰는데 \*\*읽는 방향\*\*이 달라져. 구체적으로 볼게.



\---



\# 1차 스프린트



\## 만드는 것



```

M2  JD 추출     LLM 1회 → jd\_requirements 행 N개

M2  자소서 추출  LLM 1회 → document\_claims 행 N개

M4-b 질문 생성   Director가 위 행들을 "아직 안 다룬 것" 기준으로 고름

```



`document\_claims`에서 \*\*1차에 채우는 컬럼은 4개뿐\*\*이야:



| 컬럼 | 1차 | 이유 |

| --- | --- | --- |

| `claim\_text` | ✅ | 주장 문장 |

| `claim\_type` | ✅ | tech\_decision / contribution / achievement / motivation |

| `tech\_tags` | ✅ | 주제 매칭용 |

| `paragraph\_no` | ✅ | 원문 되짚기 |

| `topic\_code` | ⏸ | `topic\_taxonomy` 완성 후 |

| `repository\_hint` | ⏸ | \*\*2차 대조의 연결고리\*\* — 1차엔 불필요 |



`repository\_hint`(이 주장이 어느 레포 얘기인지)를 1차에 안 채우는 게 포인트야. \*\*그게 대조의 열쇠인데, 1차엔 대조를 안 하니까.\*\*



\## JD가 쓰이는 곳 — 4개 지점



\*\*① M2 — 레포 추천 (핵심)\*\*



```

jd\_requirements.tech\_tags = {Redis, Spring Boot}

&#x20;       ↕ 대조

repo\_analyses(shallow).tech\_stack = \[{name:"Redis", source:"README"}]

&#x20;       ↓

repo\_match\_scores.matched\_requirement\_ids = {req\_3, req\_7}

```



→ 이게 5a-v2의 `"💡 공고의 Redis 캐싱 경험과 직접 연관"` 문구 원천



\*\*② M3 — 5a-v2 우측 리스트\*\*



```

공고 요구사항

&#x20; \[필수] Spring Boot 기반 API 개발 경험 3년 이상

&#x20; \[필수] Redis 등 캐시 시스템 운영 경험

&#x20; \[우대] 대용량 트래픽 처리 경험

```



`display\_order` 순, 읽기 전용 (편집 불가 확정)



\*\*③ M4-b — 질문 소재 선택\*\*



```

Director 컨텍스트:

&#x20; 다룬 요구사항   : {req\_1, req\_3}

&#x20; 안 다룬 요구사항: {req\_2, req\_5, req\_7}   ← 여기서 다음 질문 고름

&#x20;       ↓

Q: "공고에서 대용량 트래픽 처리 경험을 요구하는데, 어떤 경험이 있으신가요?"

&#x20;       ↓

interview\_turns에 "이 질문은 req\_5 기반" 기록

```



\*\*④ M6 — 커버리지 점수\*\*



```

Company·Job Fit

&#x20; 요구사항 8개 중 5개가 면접에서 다뤄짐

&#x20; 미검증: req\_2(Kafka), req\_5(Kubernetes), req\_8(MSA)

```



\## 자소서가 쓰이는 곳 — 2개 지점



\*\*① M4-b — 질문 소재\*\*



```

claim\_2 "결제 모듈을 단독으로 설계·구현했습니다" (contribution, 미사용)

&#x20;       ↓

Q: "결제 모듈을 단독으로 구현하셨다고 하셨는데,

&#x20;   설계에서 가장 고민했던 부분은 무엇인가요?"

```



\*\*② M6 — 커버리지\*\*



```

자소서 주장 6개 중 3개가 면접에서 다뤄짐

```



\## 1차의 실제 가치 — 커버리지 추적



`interview\_sessions.context\_state`가 이렇게 채워져:



```json

{

&#x20; "covered\_requirement\_ids": \["req\_1", "req\_3"],

&#x20; "pending\_requirement\_ids": \["req\_2", "req\_5", "req\_7", "req\_8"],

&#x20; "covered\_claim\_ids": \["claim\_2"],

&#x20; "pending\_claim\_ids": \["claim\_1", "claim\_3", "claim\_4"]

}

```



\*\*이것만으로도 Director가 "무엇을 아직 안 물었나"를 알 수 있어.\*\* 이게 없으면 LLM이 같은 주제를 반복하거나 중요한 요구사항을 빼먹어도 감지가 안 돼.



원문 한 덩어리면 이 체크리스트를 만들 수 없어 — 항목에 ID가 없으니까. \*\*이게 1차에서 claim/requirement가 필요한 이유야.\*\* 대조가 아니라 체크리스트 때문.



\## 1차 질문의 성격



```

✅ 가능: "공고에서 Redis 경험을 요구하는데, 어떤 경험이 있으신가요?"      (JD 소재)

✅ 가능: "결제 모듈을 단독 구현하셨다는데, 어떻게 설계하셨나요?"          (자소서 소재)

✅ 가능: "RedisConfig.java에서 TTL을 30분으로 두셨는데 근거가 뭔가요?"    (코드 근거)



❌ 불가: "자소서엔 트래픽 분석해서 정했다는데, 코드는 고정값이네요?"      (대조)

```



세 종류가 \*\*각자 따로\*\* 나와. 서로 엮이지 않아.



\---



\# 2차 스프린트



\## 추가하는 것



```

1\. document\_claims.repository\_hint 채우기       ← 연결고리

2\. claim ↔ evidence 대조 로직

3\. evidence\_conflicts 행 생성

4\. jd\_requirements ↔ verified tech\_stack 정밀 매칭

```



\## ① 자소서 축 — 대조가 켜짐



```

claim\_1  "트래픽 패턴을 분석해 TTL을 30분으로 설정했습니다"

&#x20;        tech\_tags = {Redis, TTL}

&#x20;        repository\_hint = devon-backend        ← 2차에 채워짐

&#x20;                   ↓

&#x20;        Evidence Tool 호출: devon-backend에서 TTL 관련 설정 찾기

&#x20;                   ↓

evidence  "application.yml: ttl: 30m (고정값, 동적 조정 코드 없음)"

&#x20;                   ↓

&#x20;        claim과 evidence가 어긋남 감지

&#x20;                   ↓

evidence\_conflicts 행 생성

&#x20;   claim\_id, evidence\_id, conflict\_type='claim\_not\_supported'

&#x20;                   ↓

Q: "자소서에 트래픽 분석 후 TTL을 정하셨다고 쓰셨는데,

&#x20;   코드에는 30분이 하드코딩되어 있네요. 어떤 분석이었나요?"

&#x20;                   ↓

리포트: "기술 판단 주장이 코드로 뒷받침되지 않음 (자소서 2문단)"

```



\## ② JD 축 — 매칭 정밀도가 올라감



이쪽도 2차 업그레이드가 있어. 1차 매칭은 \*\*L1 shallow 기반\*\*이라 근거가 약해:



|  | 1차 | 2차 |

| --- | --- | --- |

| 근거 | `tech\_stack.source = "README"` | `tech\_stack.verified = true`, `source = "RedisConfig.java:24"` |

| 의미 | \*\*"README에 Redis라고 써 있음"\*\* | \*\*"코드에 Redis가 실제로 있음"\*\* |

| 매칭 결과 | 과대 매칭 위험 | 정확 |



그리고 L2의 `verified:false`가 리포트로 연결돼:



```

공고 요구사항 req\_7 "Redis 운영 경험"

&#x20; → 레포 tech\_stack: Kafka(verified:false, README에만 언급)

&#x20; → "공고가 요구하는 X를 이력에 적으셨으나 코드에서 확인되지 않음"

```



\## 2차 질문의 성격



```

1차: "TTL을 어떻게 정하셨나요?"                    ← 소재

2차: "자소서엔 분석했다는데 코드는 고정값이네요?"    ← 대조

```



\*\*같은 주제인데 질문의 날카로움이 달라져.\*\* 두 번째가 실제 면접관이 하는 질문이야.



\---



\# 스프린트 경계



| 항목 | 1차 | 2차 |

| --- | --- | --- |

| \*\*테이블\*\* |  |  |

| `job\_postings` | ✅ 전체 | 사이트 어댑터 추가 |

| `jd\_requirements` | ✅ 전체 | — |

| `user\_documents` | ✅ 업로드 + 텍스트 추출 | — |

| `document\_claims` | ✅ 생성 (4컬럼) | `repository\_hint`, `topic\_code` 채움 |

| `evidence\_conflicts` | ⏸ \*\*테이블만, 행 생성 안 함\*\* | ✅ 행 생성 |

| \*\*로직\*\* |  |  |

| 요구사항/주장 커버리지 추적 | ✅ | — |

| 질문 소재 선택 | ✅ | — |

| claim ↔ evidence 대조 | ⏸ | ✅ |

| verified 기반 정밀 매칭 | ⏸ | ✅ |

| \*\*LLM 호출 (M2 기준)\*\* | JD 1회 + 자소서 1회 | + 대조 판정 |



\## 1차에 `evidence\_conflicts` 테이블은 만들되 비워둘 것



행은 안 생기지만 \*\*테이블은 1차에 만들어두는 게 좋아.\*\* 이유:



\- FK가 `document\_claims`와 `evidences` 양쪽을 참조하는데, 2차에 추가하면 그 시점의 데이터 정합성을 다시 봐야 해

\- 빈 테이블 하나 비용은 0이야



\---



\# 왜 이 분할이 안전한가



\*\*1차에서 만든 데이터가 2차에 그대로 쓰여.\*\* 버리는 게 없어:



```

1차에 쌓인 것                    2차에 하는 일

─────────────────────────────────────────────

document\_claims 행 N개      →   repository\_hint만 UPDATE

jd\_requirements 행 N개      →   그대로 사용

evidences (Tool 산출)       →   claim과 연결

repo\_analyses(deep).verified →  매칭에 반영

```



만약 1차에 claim을 안 만들고 원문만 뒀다면, 2차에 \*\*과거 사용자 전원의 자소서를 재분해\*\*해야 해. `paragraph\_no` 같은 원문 위치 정보는 원문이 남아 있으니 복원 가능하지만, 이미 끝난 면접의 "어느 주장이 다뤄졌나"는 \*\*소급 복원이 불가능\*\*해.



이게 `document\_claims`를 1차에 넣자고 한 진짜 이유야 — 대조 때문이 아니라 \*\*소급 불가 데이터\*\*라서.



\---



\# 1차에 확인이 필요한 것 2개



\*\*① `document\_claims` 개수 상한\*\*

자소서 3,000자를 문장 단위로 쪼개면 20\~40개가 나올 수 있어. 그걸 다 Director 컨텍스트에 넣으면 토큰도 크고, "미사용 주장"이 너무 많아서 커버리지 지표가 의미를 잃어.



→ \*\*claim\_type이 `tech\_decision` / `contribution`인 것만 추출\*\*하고 `motivation`(지원동기)은 버리는 게 나을 것 같아. 면접 질문 소재로 쓸 수 있는 건 앞의 둘뿐이야. 상한은 10개 정도.



\*\*② 포트폴리오는 `document\_claims`를 만드나?\*\*`user\_documents.kind = 'portfolio'`이고 `source\_type='link'`면 텍스트 추출이 안 돼 (`extract\_status='unsupported'`가 정상). 그럼 claim도 없어.



→ \*\*포트폴리오는 1차에 claim 추출 대상에서 제외\*\*하고, 자소서(`cover\_letter`)만 하는 게 맞아 보여. 포폴은 "제출했다"는 사실만 기록.



\### \[TABLE] job\_postings



| 필드 | 타입 | 제약 | 설명 | 활용 |

| --- | --- | --- | --- | --- |

| id | UUID | PK, default gen\_random\_uuid() |  |  |

| user\_id | UUID | FK users, NOT NULL |  |  |

| source\_type | VARCHAR(10) | NOT NULL DEFAULT 'url' | `url`. 확장 대비 `text` 값 예약 | 화면은 URL 단일 |

| source\_url | TEXT | NULL | 사용자가 입력한 원본 URL | 재사용 키 |

| site\_adapter | VARCHAR(30) | NULL | `wanted` / `saramin` / `jobkorea` / `generic` | \*\*2차 어댑터별 성공률 비교 축\*\* |

| fetch\_url | TEXT | NULL | 실제 호출한 URL (`/api/chaos/jobs/v1/{id}/details`) | 재현·디버깅 |

| raw\_text | TEXT | NULL | 어댑터가 뽑은 텍스트. LLM 입력 원본 | 추출 오류 시 대조 |

| source\_image\_urls | TEXT\[] | NULL | 이미지형 공고일 때 LLM에 첨부한 URL | 사람인 확장 시 필수 |

| content\_form | VARCHAR(10) | NULL | `text` / `image` / `mixed` — \*\*페이지의 실제 형태\*\* | \*\*2차 우선순위 판단\*\* |

| company\_name | VARCHAR(100) | NULL | 추출값 | 리포트 표기 |

| industry | VARCHAR(50) | NULL | 도메인리더 페르소나 필수.

원티드 api의 industry\_name | 면접 질문에서 도메인 persona가 활용 |

| position\_title | VARCHAR(150) | NULL | 추출값 | `interview\_reports.position\_label` |

| parse\_status | VARCHAR(20) | NOT NULL DEFAULT 'pending' | `pending`/`success`/`partial`/`failed` | 진행률·재시도 |

| parse\_error\_code | VARCHAR(50) | NULL | 아래 표 | 4-3-v2 문구 분기 |

| model | VARCHAR(50) | NULL | 추출 모델 | Eval |

| prompt\_version | VARCHAR(20) | NULL |  | \*\*Eval 축 + 재추출 판정\*\* |

| input\_tokens | INT | NULL |  | 이미지 공고 비용 실측 |

| latency\_ms | INT | NULL |  | 2차 투자 판단 근거 |

| raw\_output | JSONB | NULL | LLM 응답 원문 | \*\*파싱 실패 시 재호출 없이 복구\*\* |

| fetched\_at | TIMESTAMPTZ | NULL | 페이지 수집 시각 | \*\*재사용 TTL\*\* |

| created\_at / updated\_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |  |  |



```

UNIQUE (user\_id, source\_url)

CHECK  (source\_type  IN ('url','text'))

CHECK  (content\_form IN ('text','image','mixed'))

CHECK  (parse\_status IN ('pending','success','partial','failed'))

INDEX  (user\_id, created\_at DESC)

```



\#### parse\_error\_code



| 코드 | 단계 | 상황 | 화면 |

| --- | --- | --- | --- |

| `unsupported\_site` | 우리 | 어댑터 없는 사이트 | "지원하지 않는 사이트예요" → 공고 없이 진행 유도 |

| `url\_unreachable` | 우리 | 404·마감·네트워크 | "공고를 불러올 수 없어요" |

| `content\_empty` | 우리 | 텍스트·이미지 둘 다 없음 | 동일 |

| `not\_a\_job\_posting` | LLM | 공고가 아니라 판정 | "채용 공고가 아닌 것 같아요" |

| `extraction\_failed` | LLM | 요구사항 0건 | "공고를 분석하지 못했어요" |

| `llm\_timeout` / `parse\_failed` | LLM |  | 자동 1회 재시도 |

| `input\_too\_large` | LLM | 컨텍스트 초과 | 2차(이미지 공고) |



\*\*단계가 나뉘는 게 핵심이야\*\* — `unsupported\_site`는 재시도해도 소용없고(사이트를 지원해야 함), `llm\_timeout`은 재시도하면 되니까 화면 대응이 달라.



\#### 공고 재사용 규칙 추천 (M2)



```

fetched\_at 이 7일 이내 AND parse\_status='success'

&#x20; → 행 재사용, LLM 호출 0회

그 외

&#x20; → 재fetch + 재추출, jd\_requirements DELETE 후 재INSERT

```



\### \[TABLE] jd\_requirements



| 필드 | 타입 | 제약 | 설명 | 활용 |

| --- | --- | --- | --- | --- |

| id | UUID | PK, default gen\_random\_uuid() |  | \*\*참조 대상 — 이 테이블의 존재 이유\*\* |

| job\_posting\_id | UUID | FK job\_postings ON DELETE CASCADE, NOT NULL |  |  |

| category | VARCHAR(20) | NOT NULL | `required` / `preferred` / `responsibility` | M3 리스트 그룹핑, 채점 가중치 |

| text | TEXT | NOT NULL | 요구사항 한 줄 (원문 유지) | M3 표시, 질문 생성 입력 |

| normalized\_keyword | VARCHAR(100) | NULL | 매칭용 정규화 키 | 표기 흔들림 흡수 (`Spring Boot`/`springboot`) |

| tech\_tags | TEXT\[] | NULL | `{Redis, Spring Boot}` | \*\*M2 레포 매칭의 대조 키\*\* |

| confidence | NUMERIC(3,2) | NULL | LLM 추출 신뢰도 | 저신뢰 항목 가중치 하향 |

| extracted\_from | VARCHAR(10) | NULL | `text` / `image` | \*\*이미지 추출 품질 측정\*\* (2차) |

| display\_order | INT | NOT NULL | 화면 순서 | M3 우측 리스트 |

| created\_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |  |  |



```

INDEX (job\_posting\_id, display\_order)

CHECK (category IN ('required','preferred','responsibility'))

```



\#### 원티드 필드 매핑 (1차 대상 확정 시)



| 원티드 | category | 비고 |

| --- | --- | --- |

| `requirements` | `required` |  |

| `preferred\_points` | `preferred` |  |

| `main\_tasks` | `responsibility` |  |

| `skill\_tags` | → `tech\_tags` 원천 | \*\*LLM 추측 불필요\*\* |

| `intro`, `benefits` | 저장 안 함 | 질문 소재로 부적합 |



\### \[TABLE] user\_documents



| 필드 | 타입 | 제약 | 설명 | 활용 |

| --- | --- | --- | --- | --- |

| id | UUID | PK, default gen\_random\_uuid() |  |  |

| user\_id | UUID | FK users, NOT NULL |  |  |

| session\_id | UUID | FK interview\_sessions, NULL | \*\*M2에는 세션이 아직 없어서 NULL\*\*. M4 세션 생성 시 연결 | 어느 면접에 쓰였나 |

| kind | VARCHAR(20) | NOT NULL | `cover\_letter` / `portfolio` | \*\*claim 추출 여부를 가르는 키\*\*

1차에서는 자소서만 claim 추출. |

| source\_type | VARCHAR(10) | NOT NULL | `file` / `link` |  |

| link\_url | TEXT | NULL | `source\_type='link'`일 때 | 포폴 링크 |

| file\_name | VARCHAR(255) | NULL | `source\_type='file'`일 때 | 화면 표시 |

| mime\_type | VARCHAR(100) | NULL | `application/pdf` 등 | 추출기 선택 |

| size\_bytes | INT | NULL | 자소서 10MB / 포폴 20MB 상한 | 업로드 검증 |

| storage\_uri | TEXT | NULL | \*\*1차 NULL — 파일 미저장\*\* | 2차 |

| extracted\_text | TEXT | NULL | 추출 원문 | \*\*claim의 원본. 대조·검증 시 되짚기\*\* |

| extract\_status | VARCHAR(20) | NOT NULL DEFAULT 'pending' | `pending`/`success`/`failed`/`unsupported` |  |

| \*\*mentioned\_repo\_urls\*\* | TEXT\[] | NULL | ★ 포폴에서 파싱한 GitHub URL 원문 | \*\*M2 후보 합집합 + M3 배지\*\* |

| created\_at / updated\_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |  |  |



```

INDEX (user\_id, kind)

CHECK (kind        IN ('cover\_letter','portfolio'))

CHECK (source\_type IN ('file','link'))

CHECK (extract\_status IN ('pending','success','failed','unsupported'))

```



\#### kind별 처리 방식



|  | `cover\_letter` | `portfolio` |

| --- | --- | --- |

| 텍스트 추출 | ✅ | ✅ (링크면 `unsupported`) |

| \*\*claim 추출\*\* | ✅ `tech\_decision`/`contribution` | \*\*❌ 안 함 (확정)\*\* |

| \*\*GitHub URL 파싱\*\* | ❌ | ✅ `mentioned\_repo\_urls` |

| Director 컨텍스트 | 원문 + claim | \*\*들어가지 않음\*\* |

| 역할 | 질문 소재 | \*\*레포 추천 신호\*\* |



> 포폴이 `source\_type='link'`면 텍스트 추출이 안 되니 `mentioned\_repo\_urls`도 못 채워.

다만 \*\*링크 자체가 GitHub URL이면\*\* 그걸 그대로 넣으면 돼 

(`github.com/kim` 프로필 링크거나 `github.com/kim/repo`거나).

> 



`extract\_status='unsupported'`는 \*\*실패가 아니라 정상\*\*이야 — 기존 문서에도 명시돼 있어.



\---



\### \[TABLE] document\_claims



| 필드 | 타입 | 제약 | 설명 | 스프린트 |

| --- | --- | --- | --- | --- |

| id | UUID | PK, default gen\_random\_uuid() | \*\*참조 대상\*\* | 1차 |

| document\_id | UUID | FK user\_documents ON DELETE CASCADE, NOT NULL | `kind='cover\_letter'`만 | 1차 |

| paragraph\_no | SMALLINT | NULL | 원문 위치 | 1차 — \*\*claim이 의심될 때 원문 되짚기\*\* |

| claim\_text | TEXT | NOT NULL | 주장 한 문장 | 1차 — 질문 생성 입력 |

| claim\_type | VARCHAR(30) | NOT NULL | \*\*1차 추출: `tech\_decision`, `contribution`\*\*

값 예약: `achievement`, `motivation` | 1차 |

| tech\_tags | TEXT\[] | NULL | `{Redis, TTL}` | 1차 — 주제 매칭 |

| confidence | NUMERIC(3,2) | NULL | 추출 신뢰도 | 1차 |

| \*\*topic\_code\*\* | VARCHAR(50) | FK topic\_taxonomy, NULL |  | ⏸ \*\*2차\*\* |

| \*\*repository\_hint\*\* | UUID | FK repositories, NULL | 이 주장이 어느 레포 얘기인지 | ⏸ \*\*2차 — 대조의 열쇠\*\* |

| created\_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |  | 1차 |



```

INDEX (document\_id, paragraph\_no)

CHECK (claim\_type IN ('tech\_decision','contribution','achievement','motivation'))

```



\#### claim\_type을 2개로 제한한 이유



| 타입 | 예시 | 면접 질문이 되나 |

| --- | --- | --- |

| `tech\_decision` | "트래픽을 분석해 TTL을 30분으로 설정했습니다" | ✅ \*\*검증 가능\*\* |

| `contribution` | "결제 모듈을 단독 설계·구현했습니다" | ✅ \*\*검증 가능\*\* |

| `achievement` | "응답속도를 40% 개선했습니다" | △ 수치 검증이 어려움 |

| `motivation` | "사용자 경험에 관심이 많습니다" | ❌ 코드와 무관 |



\*\*앞의 둘만 GitHub Evidence와 대조가 가능해.\*\* 뒤의 둘은 질문 소재로도 약하고 2차 대조 대상도 안 돼서, 추출해봐야 커버리지 지표만 희석시켜.



> CHECK에는 4개를 다 남겨둬. 2차에 `achievement`를 열 수도 있고, 값 추가는 CHECK 수정이 필요하니까 미리 열어두는 게 편해.

> 



\#### 스프린트별 계획



\### 1차 활용 — 커버리지 체크리스트



```

interview\_sessions.context\_state

{

&#x20; "pending\_claim\_ids": \["claim\_1", "claim\_3"],

&#x20; "covered\_claim\_ids": \["claim\_2"]

}

```



```

Q: "결제 모듈을 단독으로 구현하셨다고 하셨는데,

&#x20;   설계에서 가장 고민했던 부분은 무엇인가요?"

&#x20;   ← claim\_2 기반. 질문 후 covered로 이동

```



\### 2차 확장 — `repository\_hint`가 채워지면 대조가 켜짐



```

claim\_1 "트래픽 분석해 TTL 30분 설정"  +  repository\_hint = devon-backend

&#x20;             ↓ Evidence Tool

evidence "application.yml: ttl: 30m (고정값, 동적 조정 없음)"

&#x20;             ↓

evidence\_conflicts 행 생성

&#x20;             ↓

Q: "자소서엔 분석 후 정했다는데 코드는 고정값이네요. 어떤 분석이었나요?"

```



\*\*1차에 `claim\_text`를 안 쌓아두면 2차에 과거 면접의 커버리지를 소급 복원할 수 없어.\*\* 이게 claim을 1차에 넣는 이유고, `repository\_hint` 하나만 2차에 UPDATE하면 대조가 켜져.



\### \[TABLE] analysis\_jobs → 비동기 작업 보여주는 테이블(진행 중 화면)



| \*\*필드\*\* | \*\*타입\*\* | \*\*제약\*\* | \*\*설명\*\* |

| --- | --- | --- | --- |

| id | UUID | PK, default gen\_random\_uuid() |  |

| user\_id | UUID | FK users, NOT NULL |  |

| github\_account\_id | UUID | FK, NULL |  |

| job\_posting\_id | UUID | FK, NULL | 초기에는 NULL 상태 |

| session\_id | UUID | FK interview\_sessions, NULL | `deep\_analysis`일 때만 |

| \*\*job\_type\*\* | VARCHAR(30) | NOT NULL | `initial\_sync`(M1) / `interview\_prep`(M2) / `deep\_analysis`(M4-a) |

| status | VARCHAR(20) | NOT NULL DEFAULT 'queued' | `queued`/`running`/`succeeded`/`partial`/`failed`/`canceled` |

| steps | JSONB | NOT NULL | 진행 체크리스트 원천 |

| current\_step | VARCHAR(30) | NULL |  |

| progress | SMALLINT | NOT NULL DEFAULT 0 | 0\~100 |

| error\_code | VARCHAR(50) | NULL | \*\*작업 전체\*\* 실패 |

| error\_message | TEXT | NULL |  |

| retry\_count | SMALLINT | NOT NULL DEFAULT 0 |  |

| started\_at / finished\_at | TIMESTAMPTZ | NULL |  |

| created\_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |  |



```

CHECK (job\_typeIN ('initial\_sync','interview\_prep','deep\_analysis'))

CHECK (statusIN ('queued','running','succeeded','partial','failed','canceled'))

INDEX (user\_id, created\_atDESC)



\-- 중복 실행 방지 (선택)

CREATEUNIQUE INDEXON analysis\_jobs (user\_id, job\_type)

WHEREstatusIN ('queued','running');

```



\#### \*\*steps — `interview\_prep` (포폴 반영 최신)\*\*



```

\[

{"key":"doc\_extract","label":"첨부 문서 분석","status":"done"},

{"key":"repo\_select","label":"레포 선별","status":"done"},

{"key":"repo\_detail","label":"레포 상세 수집","status":"done"},

{"key":"jd\_fetch","label":"공고 페이지 수집","status":"done"},

{"key":"jd\_extract","label":"공고 분석","status":"running"},

{"key":"repo\_analyze","label":"레포 기본 분석","status":"pending"},

{"key":"match\_score","label":"매칭 점수 계산","status":"pending"}

]

```



\#### error\_code



```

레포:  no\_public\_repo / user\_not\_found / rate\_limited / token\_invalid

공고:  jd\_fetch\_failed / jd\_extraction\_failed / not\_a\_job\_posting

문서:  doc\_extract\_failed

공통:  llm\_timeout

```



`jd\_fetch\_failed`(우리 코드)와 `jd\_extraction\_failed`(LLM)를 나눈 게 핵심 — 재시도 가능 여부가 달라.



\### JD 쪽에서의 스프린트 경계 최종



\## 스프린트 경계 최종



|  | 1차 | 2차 |

| --- | --- | --- |

| `job\_postings` | ✅ 원티드 어댑터 1종 | 사람인·잡코리아 어댑터, 이미지 처리 |

| `jd\_requirements` | ✅ 전체 (상한 20개) | `extracted\_from` 활용한 품질 측정 |

| `user\_documents` | ✅ 업로드·추출·URL 파싱 | `storage\_uri` 파일 저장 |

| `document\_claims` | ✅ 2개 타입, 6컬럼 | `repository\_hint`·`topic\_code` 채움 |

| `evidence\_conflicts` | ⏸ \*\*테이블만 생성, 행 없음\*\* | ✅ 대조 로직 |

| LLM 호출 (M2) | JD 1회 + 자소서 claim 1회 | + 대조 판정 |



\## 4. 매칭 후 레포 추천



\### \[TABLE] \*\*repo\_match\_scores\*\*



| \*\*필드\*\* | \*\*언제 쓰나\*\* | \*\*용도\*\* |

| --- | --- | --- |

| `analysis\_job\_id` | M2 쓰기 | \*\*어느 회차인지.\*\* 공고 바꿔 재분석하면 새 회차 |

| `job\_posting\_id` | M2 쓰기 | \*\*NOT NULL로 변경됨\*\* (공고 필수화) |

| `repository\_id` | M2 쓰기 / M3 읽기 |  |

| `score` | M2 쓰기 / M3 읽기 | \*\*정렬\*\* |

| `rank` | M2 쓰기 / M3 읽기 | 표시 순서 |

| `is\_ai\_recommended` | M2 쓰기 / M3 읽기 | \*\*기본 체크 여부.\*\* ★ 5개 이하로 제한 필요 |

| `reason` | M2 쓰기 / M3 읽기 | 카드의 `💡` 문구 |

| `matched\_requirement\_ids` | M2 쓰기 | \*\*어느 JD 요구사항 때문인지.\*\* M6 커버리지 계산 |

| `candidate\_source` ★ | M2 쓰기 / M3 읽기 | `rule\_filter`/`portfolio`/`both` → 📎 배지 |

| `model` / `prompt\_version` | M2 쓰기 | Eval 비교 축 |



```

UNIQUE (analysis\_job\_id, repository\_id)

```



\## 5. 면접 진행



\#### 시나리오(예시) 생성해서 DB 필드의 필요성 판단



\# 등장 데이터 (M4-a 시점)



```

users              \*\*u1  김개발\*\*

job\_postings       \*\*jp1  토스뱅크 / 백엔드 개발자 / industry='금융'\*\*

jd\_requirements    \*\*req1 \[required]  Spring Boot 기반 API 개발 3년 이상

&#x20;                  req2 \[required]  Redis 등 캐시 운영 경험

&#x20;                  req3 \[preferred] 금융권 규제 대응 경험

&#x20;                  req4 \[preferred] 대용량 트래픽 처리

&#x20;                  req5 \[respons.]  결제 도메인 서비스 개발\*\*

document\_claims    c1  "트래픽 패턴을 분석해 TTL을 30분으로 설정했습니다"  tech\_decision

&#x20;                  c2  "결제 모듈을 단독으로 설계·구현했습니다"           contribution

repositories       r1  kim/devon-backend      r2  kim/payment-service

```



\## L2 deep 분석 결과 (M4-a에서 생성)



```sql

repo\_analyses (repository\_id=r1, analysis\_level='deep', head\_sha='a3f9c2...')

&#x20; architecture\_summary = "레이어드 구조. Redis는 RedisTemplate 직접 접근,

&#x20;                         TTL은 application.yml에 30분 고정."

&#x20; notable\_areas = \[

&#x20;   {"area":"Redis TTL","path":"src/main/resources/application.yml",

&#x20;    "note":"30분 고정. 산정 근거 없음"},

&#x20;   {"area":"JWT 재발급","path":"src/main/java/.../JwtProvider.java",

&#x20;    "note":"refresh token 없이 access만 사용"}

&#x20; ]

```



\## 세션 시작



```sql

INSERT interview\_sessions

&#x20; id             = s1

&#x20; user\_id        = u1

&#x20; job\_posting\_id = jp1              -- NOT NULL (공고 필수)

&#x20; status         = 'in\_progress'

&#x20; answer\_mode    = 'text'

&#x20; max\_turns      = 9

&#x20; turn\_count     = 0

&#x20; context\_state  = {

&#x20;   "pending\_requirement\_ids": \["req1","req2","req3","req4","req5"],

&#x20;   "covered\_requirement\_ids": \[],

&#x20;   "pending\_claim\_ids": \["c1","c2"],

&#x20;   "covered\_claim\_ids": \[],

&#x20;   "pending\_topics": \["redis\_cache","jwt\_auth"],

&#x20;   "covered\_topics": \[],

&#x20;   "persona\_turn\_counts": {"tech\_lead":0,"domain\_lead":0,"hr\_manager":0},

&#x20;   "current\_persona": null, "current\_topic": null, "current\_depth": 0

&#x20; }



INSERT session\_repositories

&#x20; (s1, r1, is\_selected=true, snapshot\_head\_sha='a3f9c2...', selection\_source='ai\_kept')

&#x20; (s1, r2, is\_selected=true, snapshot\_head\_sha='7b1e88...', selection\_source='ai\_kept')

```



\---



\# Turn 1 — 테크리더 · 주제 시작



\*\*Director 판단:\*\* `pending\_topics\[0] = redis\_cache` → `notable\_areas\[0]` 사용. \*\*Tool 호출 없음.\*\*



```sql

\-- ① 근거를 evidences에 기록 (L2 부산물이라 tool\_name = NULL)

INSERT evidences

&#x20; id            = ev1

&#x20; session\_id    = s1

&#x20; repository\_id = r1

&#x20; source\_type   = 'config'

&#x20; file\_path     = 'src/main/resources/application.yml'

&#x20; git\_ref       = 'a3f9c2...'          -- session\_repositories.snapshot\_head\_sha

&#x20; snippet       = "spring:\\n  cache:\\n    redis:\\n      time-to-live: 30m"

&#x20; summary       = "TTL 30분 고정값"

&#x20; tool\_name     = NULL                  -- ★ 사전 분석 산출물

&#x20; tool\_query    = NULL

&#x20; retrieved\_for\_turn = 1



\-- ② 질문

INSERT interview\_turns

&#x20; id              = t1

&#x20; session\_id      = s1

&#x20; turn\_no         = 1

&#x20; persona         = 'tech\_lead'

&#x20; question\_text   = "Redis TTL을 30분으로 설정하셨는데, 이 값은 어떻게 정하셨나요?"

&#x20; question\_intent = 'probe\_depth'

&#x20; topic\_code      = 'redis\_cache'

&#x20; depth           = 1                   -- ★ 주제 시작

&#x20; parent\_turn\_no  = NULL

&#x20; status          = 'asked'

&#x20; jd\_requirement\_ids = {req2}           -- 공고의 "Redis 캐시 운영 경험"과 연결



INSERT turn\_evidences (t1, ev1, 'question\_basis')

```



\*\*사용자 답변\*\*



```sql

UPDATE interview\_turns SET

&#x20; answer\_text  = "트래픽을 고려해서 정했습니다."

&#x20; answered\_at  = now()

&#x20; answer\_duration\_sec = 34

&#x20; status       = 'answered'

WHERE id = t1

```



\*\*답변 분석 → Director 판단\*\*



```sql

UPDATE interview\_turns SET

&#x20; analysis = {

&#x20;   "specificity": 0.2,

&#x20;   "verified\_claims": \[],

&#x20;   "unverified\_claims": \["트래픽을 고려했다"],

&#x20;   "needs\_verification": true            -- ★ 검증 필요

&#x20; },

&#x20; decision = {

&#x20;   "action": "probe\_deeper",

&#x20;   "reason": "근거 제시 없이 추상적. 코드 확인 후 재질문",

&#x20;   "tool\_required": true,

&#x20;   "next\_persona": "tech\_lead"

&#x20; }

WHERE id = t1

```



\---



\# Turn 2 — 테크리더 · 꼬리질문 (Tool 개입)



\*\*Director:\*\* `needs\_verification=true` → \*\*Evidence Tool 호출\*\*



```

Tool 호출

&#x20; tool     = read\_file

&#x20; repo     = 'kim/devon-backend'         ← repositories.full\_name

&#x20; path     = 'src/main/resources/application.yml'  ← notable\_areas\[0].path (검색 힌트)

&#x20; ref      = 'a3f9c2...'                 ← session\_repositories.snapshot\_head\_sha

```



```sql

INSERT evidences

&#x20; id            = ev2

&#x20; session\_id    = s1

&#x20; repository\_id = r1

&#x20; source\_type   = 'code'

&#x20; file\_path     = 'src/main/java/.../RedisCacheConfig.java'

&#x20; git\_ref       = 'a3f9c2...'

&#x20; line\_start=24, line\_end=31

&#x20; snippet       = "@Bean\\npublic RedisCacheConfiguration cacheConfig() {\\n

&#x20;                  return RedisCacheConfiguration.defaultCacheConfig()\\n

&#x20;                    .entryTtl(Duration.ofMinutes(30));  // 고정\\n}"

&#x20; summary       = "TTL이 코드에 하드코딩. 동적 조정 로직 없음"

&#x20; tool\_name     = 'read\_file'            -- ★ Tool 산출물

&#x20; tool\_query    = 'application.yml, RedisCacheConfig'

&#x20; retrieved\_for\_turn = 2



INSERT interview\_turns

&#x20; id              = t2

&#x20; turn\_no         = 2

&#x20; persona         = 'tech\_lead'

&#x20; question\_text   = "확인해보니 RedisCacheConfig.java에 30분이 하드코딩되어 있고

&#x20;                    동적 조정 코드가 없는데, 트래픽이 변하면 어떻게 대응하시나요?"

&#x20; question\_intent = 'probe\_depth'

&#x20; topic\_code      = 'redis\_cache'

&#x20; depth           = 2                    -- ★ 같은 주제 안에서 깊어짐

&#x20; parent\_turn\_no  = 1                    -- ★ turn 1 답변에서 파생

&#x20; status          = 'asked'



INSERT turn\_evidences (t2, ev2, 'question\_basis')

```



\*\*답변 → 분석 → 판단\*\*



```sql

UPDATE interview\_turns SET

&#x20; answer\_text = "당시엔 트래픽이 크지 않아 고정값으로 뒀습니다.

&#x20;                커지면 프로퍼티로 빼서 환경별로 조정할 계획이었습니다."

&#x20; status      = 'answered',

&#x20; analysis    = {"specificity":0.7, "acknowledged\_limitation":true},

&#x20; decision    = {

&#x20;   "action": "switch\_topic",

&#x20;   "reason": "한계를 인지하고 대안을 제시함. 이 주제는 충분히 다룸",

&#x20;   "next\_persona": "domain\_lead"        -- ★ 페르소나 교대

&#x20; }

WHERE id = t2

```



\*\*세션 상태 갱신\*\*



```sql

UPDATE interview\_sessions SET

&#x20; turn\_count = 2,

&#x20; context\_state = {

&#x20;   "pending\_requirement\_ids": \["req1","req3","req4","req5"],

&#x20;   "covered\_requirement\_ids": \["req2"],          -- ★ req2 소진

&#x20;   "pending\_topics": \["jwt\_auth"],

&#x20;   "covered\_topics": \["redis\_cache"],            -- ★ 주제 소진

&#x20;   "persona\_turn\_counts": {"tech\_lead":2,"domain\_lead":0,"hr\_manager":0},

&#x20;   "current\_persona": "domain\_lead",

&#x20;   "current\_depth": 0

&#x20; }

WHERE id = s1

```



\---



\# Turn 3 — 도메인리더 · JD 기반



\*\*Director:\*\* 페르소나가 `domain\_lead`로 바뀜 → 근거 원천이 \*\*코드가 아니라 JD + industry\*\*



```sql

INSERT interview\_turns

&#x20; id              = t3

&#x20; turn\_no         = 3

&#x20; persona         = 'domain\_lead'

&#x20; question\_text   = "저희는 금융권이라 캐시에 개인정보가 담기면 규제 대상이 됩니다.

&#x20;                    캐시 데이터의 민감도를 고려해보신 적 있나요?"

&#x20; question\_intent = 'job\_fit'

&#x20; topic\_code      = 'compliance'

&#x20; depth           = 1                    -- ★ 새 주제라 리셋

&#x20; parent\_turn\_no  = NULL

&#x20; status          = 'asked'

&#x20; jd\_requirement\_ids = {req3}            -- "금융권 규제 대응 경험"

&#x20; -- turn\_evidences 행 없음 ← ★ 코드 근거가 없는 질문

```



> \*\*여기가 중요해.\*\* `turn\_evidences`에 행이 안 생겨. 그런데 이건 \*\*결함이 아니야\*\* — 도메인리더는 코드가 아니라 JD와 `job\_postings.industry='금융'`을 근거로 묻는 페르소나니까.

> 

> 

> Eval에서 "근거 없는 질문"을 셀 때 \*\*페르소나별로 나눠 봐야 하는 이유\*\*가 이거야. `tech\_lead`의 근거 없는 질문은 문제지만, `domain\_lead`는 `jd\_requirement\_ids`가 채워져 있으면 정상이야.

> 



\---



\# Turn 4 — 인사팀장 · 자소서 기반



```sql

INSERT interview\_turns

&#x20; id              = t4

&#x20; turn\_no         = 4

&#x20; persona         = 'hr\_manager'

&#x20; question\_text   = "결제 모듈을 단독으로 설계·구현하셨다고 쓰셨는데,

&#x20;                    팀원과 어떻게 역할을 나누셨나요?"

&#x20; question\_intent = 'verify\_contribution'

&#x20; topic\_code      = 'collaboration'

&#x20; depth           = 1

&#x20; status          = 'asked'

&#x20; claim\_ids       = {c2}                 -- ★ 자소서 주장 c2에서 나옴

```



```sql

UPDATE interview\_sessions SET

&#x20; context\_state.covered\_claim\_ids = \["c2"],

&#x20; context\_state.pending\_claim\_ids = \["c1"]

```



> \*\*1차에서는 여기까지야.\*\* c1("트래픽 분석해 TTL 설정")과 ev2(하드코딩)가 \*\*명백히 충돌하는데도\*\* `evidence\_conflicts` 행이 안 생겨. 대조 로직이 2차니까.

> 

> 

> 2차에 `document\_claims.repository\_hint = r1`이 채워지면:

> 

> ```sql

> INSERT evidence\_conflicts

>   claim\_id = c1, evidence\_id = ev2

>   source = 'doc\_vs\_code', conflict\_type = 'contradiction'

>   verdict = 'unresolved'          -- AI가 단정하지 않음

> ```

> 

> → \*"자소서엔 트래픽을 분석했다고 쓰셨는데 코드는 고정값이네요"\* 라는 질문이 나와.

> 



\---



\# 종료 (turn 9)



```sql

UPDATE interview\_sessions SET

&#x20; status = 'completed',              -- ★ North Star 산출 기준

&#x20; ended\_at = now(), elapsed\_sec = 1140, turn\_count = 9

```



\*\*이탈했다면:\*\*



```sql

&#x20; status = 'abandoned', abandoned\_at\_turn = 5

&#x20; -- turn 5는 status='asked'로 남음 (답변 없이 이탈)

```



\---



\# 리포트 (M6)



```sql

INSERT interview\_reports

&#x20; session\_id     = s1

&#x20; overall\_score  = 74.5

&#x20; position\_label = '토스뱅크 백엔드 개발자'   -- job\_postings.position\_title

&#x20; summary        = "프로젝트 구조 이해도는 높으나 기술 판단 근거 제시가 약함"



INSERT report\_scores

&#x20; (technical\_reasoning,   6.5, "TTL 산정 근거를 즉답하지 못함", evidence\_turn\_nos={1,2})

&#x20; (contribution\_clarity,  8.0, "역할 구분을 구체적으로 설명",   evidence\_turn\_nos={4})

&#x20; (company\_job\_fit,       6.0, "금융 규제 관점 고려 부족",      evidence\_turn\_nos={3})

```



\*\*커버리지 산출\*\*



```sql

\-- 요구사항 5개 중 3개 다룸 → company\_job\_fit 점수 근거

covered\_requirement\_ids = \["req2","req3","req5"]

미검증: req1(Spring Boot 경력), req4(대용량 트래픽)

```



\---



\# 이 흐름에서 각 필드가 한 일



| 필드 | 역할 |

| --- | --- |

| `context\_state` | Director의 \*\*유일한 작업 기억.\*\* 매 턴 갱신, 다음 질문 선택 근거 |

| `depth` / `parent\_turn\_no` | turn 1→2가 \*\*꼬리질문\*\*임을, turn 3이 \*\*새 주제\*\*임을 표현 |

| `evidences.tool\_name` | ev1(NULL, 사전분석) vs ev2(`read\_file`, 면접 중 조회) 구분 |

| `snapshot\_head\_sha` | Tool이 \*\*어느 커밋을 읽을지\*\* 지정 (`git\_ref`로 복사됨) |

| `notable\_areas\[].path` | Tool의 \*\*검색 시작점.\*\* 없으면 레포 전체를 뒤져야 함 |

| `turn\_evidences` | t1·t2는 근거 있음, t3는 없음 → \*\*Eval 검증 대상 식별\*\* |

| `jd\_requirement\_ids` | t1→req2, t3→req3. M6 커버리지 계산 |

| `claim\_ids` | t4→c2. 자소서 활용 추적 |

| `persona` | 근거 원천이 페르소나마다 다름을 데이터로 확인 가능 |



\### \[TABLE] session\_repositories



| 필드 | 언제 쓰나 | 용도 |

| --- | --- | --- |

| `session\_id` | M3 쓰기 |  |

| `repository\_id` | M3 쓰기 / M4 읽기 |  |

| `is\_selected` | M3 쓰기 | \*\*최대 5개.\*\* M4-a의 L2 대상 |

| `selection\_source` | M3 쓰기 | `ai\_kept`/`ai\_removed`/`user\_added` → \*\*정성 분석의 핵심\*\* |

| `was\_ai\_recommended` | M3 쓰기 | 추천 당시 값 복사 (지표용) |

| `ai\_score` / `ai\_reason` | M3 쓰기 | 추천 당시 값 \*\*복사\*\* — 나중에 재분석해도 안 바뀌게 |

| `snapshot\_head\_sha` | M3 쓰기 / \*\*M4-b 읽기\*\* | \*\*Evidence Tool의 `ref` 인자.\*\* 없으면 툴이 어느 커밋을 읽을지 모름 |

| `snapshot` | M3 쓰기 / M4-a 읽기 | 그 시점 레포 요약. Director 첫 질문 컨텍스트 |



```

UNIQUE (session\_id, repository\_id)

```



\#### 가장 중요한 두 필드



\*\*`snapshot\_head\_sha`\*\* — M4-b에서 Tool이 코드를 읽을 때 쓰는 커밋 고정값. 이게 없으면 면접 중에 사용자가 push했을 때 근거와 질문이 어긋나. \*\*동작 필수 필드\*\*야.



\*\*`selection\_source`\*\* — 위에서 말한 정성 분석의 유일한 입력. 이 값이 없으면 "왜 뺐는지"를 아예 못 봐.



\#### session\_repositories에 각 상황에 따른 필드를 놔둔 이유



\## 1. 채택률의 실제 가치 — 생각보다 낮아



\### 문제 ① 표본이 없어



아이디어톤 데모에서 사용자가 10명이면 채택률 0.7과 0.6의 차이가 \*\*통계적으로 무의미\*\*해. 프롬프트를 바꿨을 때 좋아진 건지 우연인지 구분이 안 돼.



\### 문제 ② 기본 선택이 지표를 부풀려



레포가 \*\*기본 체크된 상태로\*\* 뜨니까, 사용자가 아무 생각 없이 "확정"만 눌러도 채택률 100%가 나와. 그게 "추천이 좋다"는 증거가 아니라 그냥 \*\*관성\*\*이야.



\### 문제 ③ 5개 상한이 지표를 구조적으로 왜곡해 ★



이게 제일 커.



```

AI가 8개를 추천 → 사용자는 최대 5개만 선택 가능

→ 채택률이 구조적으로 62.5%를 못 넘어

```



\*\*추천이 아무리 좋아도 상한 때문에 낮게 나와.\*\* 이러면 숫자가 알고리즘 품질을 반영하지 않아.



> \*\*설계 제약이 하나 생겨:\*\* `is\_ai\_recommended = true`인 개수를 \*\*5개 이하로 맞춰야\*\* 채택률이 의미를 가져. 지금 정하지 않으면 지표가 처음부터 망가진 채로 쌓여.

> 



\---



\## 2. 그런데 1차에서 진짜 쓸모 있는 건 따로 있어



\*\*숫자(정량)가 아니라 목록(정성)이야.\*\*



```

SELECT r.full\_name, sr.ai\_score, sr.ai\_reason

FROM session\_repositories sr JOIN repositories r ON ...

WHERE sr.selection\_source = 'ai\_removed';

```



n=10이어도 이 목록을 직접 읽으면 바로 보여:



> "포크 레포를 추천했네" / "3년 전 프로젝트를 1순위로 올렸네" / "JD가 백엔드인데 프론트 레포를 추천했네"

> 



\*\*이게 1차에서 매칭 로직을 고치는 실제 근거야.\*\* 채택률 0.62라는 숫자는 아무것도 안 알려주지만, 뺀 레포 5개의 이름과 추천 사유는 뭘 고쳐야 할지 정확히 알려줘.



반대 방향도 마찬가지:



```

WHERE selection\_source = 'user\_added'   -- 더보기로 직접 추가한 것

```



→ \*\*룰 필터가 놓친 레포\*\*야. 필터 조건을 어떻게 바꿔야 할지 나와.



\### \[TABLE] interview\_sessions



\#### 시점 정의



면접은 턴 안에서 4번 DB를 건드려서, M4-b를 쪼갤게.



| 코드 | 시점 | 하는 일 |

| --- | --- | --- |

| \*\*M4-a\*\* | 면접 준비 | 세션 생성, L2 deep, `context\_state` 초기화 |

| \*\*T1\*\* | 턴 시작 | 질문 생성 → INSERT |

| \*\*T2\*\* | 답변 수신 | `answer\_text` UPDATE (\*\*제출 버튼 1회\*\*) |

| \*\*T3\*\* | 답변 분석 | `analysis` UPDATE |

| \*\*T4\*\* | Director 판단 | `decision` UPDATE + `context\_state` 갱신 |

| \*\*M4-end\*\* | 종료 | `status` 확정 |

| \*\*M6\*\* | 리포트 | 채점·조회 |



| 필드 | 타입 | 제약 | 설명 | 사용 시점 |

| --- | --- | --- | --- | --- |

| id | UUID | PK, default gen\_random\_uuid() |  | 쓰기 M4-a |

| user\_id | UUID | FK users, NOT NULL |  | 쓰기 M4-a / 읽기 M6 |

| \*\*job\_posting\_id\*\* | UUID | FK job\_postings, \*\*NOT NULL\*\* ★ | 공고 필수 | 쓰기 M4-a / 읽기 T1, M6 |

| \*\*status\*\* | VARCHAR(20) | NOT NULL DEFAULT 'preparing' | `preparing` / `in\_progress` / `completed` / `abandoned`<br>\*\*`paused` 없음\*\* — 세션 재개 미지원 | 쓰기 M4-a, M4-end / 읽기 M6 |

| \*\*answer\_mode\*\* | VARCHAR(10) | NOT NULL DEFAULT 'text' | 1차 `text` 고정. 2차 `voice` 추가 | 쓰기 M4-a |

| started\_at | TIMESTAMPTZ | NULL | 첫 질문 시각 | 쓰기 T1(1회차) |

| ended\_at | TIMESTAMPTZ | NULL |  | 쓰기 M4-end |

| planned\_duration\_sec | INT | NULL | 잔여시간 표시 | 읽기 T1\~T4 |

| elapsed\_sec | INT | NOT NULL DEFAULT 0 |  | 쓰기 T4 |

| max\_turns | SMALLINT | NOT NULL | \*\*종료 판정 기준\*\* | 읽기 T4 |

| turn\_count | SMALLINT | NOT NULL DEFAULT 0 |  | 쓰기 T4 |

| abandoned\_at\_turn | SMALLINT | NULL | \*\*몇 번째에서 이탈했나\*\* — 질문별 지속률 | 쓰기 M4-end |

| \*\*context\_state\*\* | JSONB | NOT NULL DEFAULT '{}' | ★ \*\*Director의 유일한 작업 기억\*\* | 쓰기 M4-a, T4 / 읽기 T1 |

| director\_prompt\_version | VARCHAR(20) | NULL |  | 쓰기 M4-a / 읽기 오프라인 |

| rubric\_version | VARCHAR(20) | NULL |  | 쓰기 M4-a / 읽기 M6 |

| model | VARCHAR(50) | NULL |  | 쓰기 M4-a |

| created\_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |  |  |



```sql

CHECK (status IN ('preparing','in\_progress','completed','abandoned'))

CHECK (answer\_mode = 'text')          -- 2차에 완화

INDEX (user\_id, created\_at DESC)

INDEX (status)                         -- North Star 집계

```



\#### context\_state 구조 (T4마다 갱신) - 면접 구조에서 제일 중요함.



```json

{

&#x20; "pending\_requirement\_ids": \["req1","req4"],

&#x20; "covered\_requirement\_ids": \["req2","req3","req5"],

&#x20; "pending\_claim\_ids": \["c1"],

&#x20; "covered\_claim\_ids": \["c2"],

&#x20; "pending\_topics": \["jwt\_auth"],

&#x20; "covered\_topics": \["redis\_cache","compliance"],

&#x20; "unverified\_claims": \["트래픽 기준 TTL 설정"],

&#x20; "persona\_turn\_counts": {"tech\_lead":2,"domain\_lead":1,"hr\_manager":1},

&#x20; "current\_persona": "hr\_manager",

&#x20; "current\_topic": "collaboration",

&#x20; "current\_depth": 1

}

```



\*\*JSONB인 이유:\*\* Director 구현이 1차 내내 바뀔 영역(원칙 5). 



\---



\### \[TABLE] interview\_turns — 면접 기록의 중심



| 필드 | 타입 | 제약 | 설명 | 사용 시점 |

| --- | --- | --- | --- | --- |

| id | UUID | PK, default gen\_random\_uuid() |  | 쓰기 T1 |

| session\_id | UUID | FK interview\_sessions, NOT NULL |  | 쓰기 T1 |

| turn\_no | SMALLINT | NOT NULL | 1부터 | 쓰기 T1 / 읽기 M6 |

| \*\*persona\*\* | VARCHAR(20) | NOT NULL | `tech\_lead` / `hr\_manager` / `domain\_lead` ★값 변경 | 쓰기 T1 / 읽기 M6 |

| question\_text | TEXT | NOT NULL |  | 쓰기 T1 / 읽기 M6 |

| question\_intent | VARCHAR(30) | NULL | `probe\_depth` / `verify\_contribution` / `compare\_alternative` / `switch\_topic` / `job\_fit` / `clarify` | 쓰기 T1 |

| \*\*topic\_code\*\* | VARCHAR(50) | NULL, \*\*1차 FK 없음\*\* ★ | `topic\_taxonomy` 확정 후 2차에 FK 추가 | 쓰기 T1 / 읽기 T4 |

| \*\*depth\*\* | SMALLINT | NOT NULL DEFAULT 1 | \*\*1=주제 시작, 2+=꼬리질문\*\*<br>"충분히 깊게 묻는가" 측정값 | 쓰기 T1 / 읽기 T4, M6 |

| parent\_turn\_no | SMALLINT | NULL | 어느 답변에서 파생됐나 | 쓰기 T1 |

| asked\_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |  | 쓰기 T1 |

| answer\_text | TEXT | NULL | \*\*제출 시 1회 저장\*\* (초안 저장 없음) | 쓰기 T2 |

| answered\_at | TIMESTAMPTZ | NULL |  | 쓰기 T2 |

| answer\_duration\_sec | INT | NULL | 질문\~제출 경과 | 쓰기 T2 |

| \*\*status\*\* | VARCHAR(20) | NOT NULL DEFAULT 'asked' | `asked` / `answered` / `skipped` / `timeout`<br>\*\*`asked`로 남은 게 곧 이탈 지점\*\* | 쓰기 T1, T2 / 읽기 M6 |

| analysis | JSONB | NULL | AnswerAnalysis (계약 2.3) | 쓰기 T3 / 읽기 T4, M6 |

| decision | JSONB | NULL | DirectorDecision (계약 2.4) | 쓰기 T4 |

| jd\_requirement\_ids | UUID\[] | NULL | 이 질문이 참조한 JD 요구사항 | 쓰기 T1 / 읽기 M6 |

| claim\_ids | UUID\[] | NULL | 이 질문이 참조한 자소서 주장 | 쓰기 T1 / 읽기 M6 |



```sql

UNIQUE (session\_id, turn\_no)

INDEX  (session\_id, turn\_no)

CHECK  (persona IN ('tech\_lead','hr\_manager','domain\_lead'))

CHECK  (status  IN ('asked','answered','skipped','timeout'))

```



> `analysis` / `decision`을 JSONB로 두되 \*\*계약 2.3/2.4의 키 이름은 지금 고정\*\*해.

2차에 `answer\_analyses` / `director\_decisions` 테이블로 승격할 때 컬럼명이 그대로여야 마이그레이션이 단순해.

> 



\#### depth의 동작



```

turn 1  depth 1  parent NULL   "TTL을 어떻게 정하셨나요?"          주제 시작

turn 2  depth 2  parent 1      "코드는 고정값인데요?"              꼬리

turn 3  depth 1  parent NULL   "금융권 규제를 고려하셨나요?"        새 주제 → 리셋

```



\*\*평균 depth가 1.2면 꼬리질문이 거의 없다는 뜻\*\*이고, 그건 이 서비스의 실패야. M6에서 반드시 봐야 할 지표.



\---



\### \[TABLE] evidences — 세션 단위 근거 풀



| 필드 | 타입 | 제약 | 설명 | 사용 시점 |

| --- | --- | --- | --- | --- |

| id | UUID | PK |  | 쓰기 T1 |

| session\_id | UUID | FK, NOT NULL | 세션 스코프 (스냅샷 원칙) | 쓰기 T1 |

| repository\_id | UUID | FK repositories, NOT NULL |  | 쓰기 T1 |

| source\_type | VARCHAR(20) | NOT NULL | `code` / `readme` / `commit` / `config` / `tree` | 쓰기 T1 |

| file\_path | TEXT | NULL |  | 쓰기 T1 / 읽기 M6 |

| \*\*git\_ref\*\* | VARCHAR(40) | NOT NULL | 커밋 SHA. \*\*없으면 재조회 불가\*\*<br>`session\_repositories.snapshot\_head\_sha`에서 복사 | 쓰기 T1 |

| line\_start / line\_end | INT | NULL |  | 쓰기 T1 |

| snippet | TEXT | NULL | \*\*원문 그대로\*\* | 쓰기 T1 / 읽기 M6 |

| summary | TEXT | NULL | LLM 요약 | 쓰기 T1 |

| relevance | NUMERIC(4,3) | NULL |  | 쓰기 T1 |

| retrieved\_for\_turn | SMALLINT | NULL | 몇 번째 턴 때문에 조회했나 | 쓰기 T1 |

| \*\*tool\_name\*\* | VARCHAR(50) | \*\*NULL 허용 명시\*\* ★ | \*\*NULL = L2 사전분석 부산물\*\*<br>\*\*값 있음 = 면접 중 Tool 호출\*\* | 쓰기 T1 / 읽기 오프라인 |

| tool\_query | TEXT | NULL |  | 쓰기 T1 |

| created\_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |  |  |



```sql

INDEX (session\_id)

INDEX (session\_id, repository\_id)

```



\#### `tool\_name` NULL 구분이 만드는 지표



```sql

SELECT CASE WHEN tool\_name IS NULL THEN '사전분석' ELSE 'Tool호출' END, COUNT(\*)

FROM evidences WHERE session\_id = ? GROUP BY 1;

```



\*\*Tool 호출이 0이면 꼬리질문이 근거 없이 나오고 있다\*\*는 뜻이야.

Agent→Tool 전환이 실제로 작동하는지 확인하는 유일한 수단.



\---



\### \[TABLE] turn\_evidences — 사용 기록



| 필드 | 타입 | 제약 | 설명 | 사용 시점 |

| --- | --- | --- | --- | --- |

| turn\_id | UUID | FK interview\_turns, PK 구성 |  | 쓰기 T1, M6 |

| evidence\_id | UUID | FK evidences, PK 구성 |  | 쓰기 T1, M6 |

| usage | VARCHAR(20) | PK 구성 | `question\_basis`(T1) / `evaluation\_basis`(M6) |  |



```sql

PRIMARY KEY (turn\_id, evidence\_id, usage)

```



\*\*같은 evidence가 두 역할을 다 할 수 있어서\*\* `usage`가 PK에 들어가. 

질문의 근거이면서 채점 근거이기도 한 경우를 구분하기 위함.



\#### 이 테이블의 존재 이유



```sql

\-- 근거 없이 생성된 질문

SELECT t.turn\_no, t.persona, t.question\_text

FROM interview\_turns t

LEFT JOIN turn\_evidences te ON te.turn\_id = t.id

WHERE t.session\_id = ? AND te.turn\_id IS NULL;

```



\*\*단, 페르소나별로 나눠 봐야 해:\*\*



| persona | 근거 없음이 | 정상 조건 |

| --- | --- | --- |

| `tech\_lead` | \*\*결함\*\* | `turn\_evidences` 있어야 함 |

| `domain\_lead` | 정상 | `jd\_requirement\_ids` 있으면 OK |

| `hr\_manager` | 정상 | `claim\_ids` 있으면 OK |



\---



\### \[TABLE] evidence\_conflicts — 1차에선 구현 X → 빈 테이블



| 필드 | 타입 | 설명 | 스프린트 |

| --- | --- | --- | --- |

| id | UUID | PK |  |

| turn\_id | UUID | FK, NULL | 답변 중 발생한 충돌 |

| evidence\_id | UUID | FK, NOT NULL |  |

| claim\_id | UUID | FK document\_claims, NULL | \*\*자소서 주장과의 충돌\*\* |

| source | VARCHAR(20) | `answer\_vs\_code` / `doc\_vs\_code` / `answer\_vs\_doc` |  |

| conflict\_type | VARCHAR(20) | `contradiction` / `not\_found` / `attribution` |  |

| claim\_text | TEXT | 사용자 주장 원문 (스냅샷) |  |

| evidence\_text | TEXT | Evidence 원문 (스냅샷) |  |

| verdict | VARCHAR(20) | \*\*DEFAULT 'unresolved'\*\* — AI가 단정하지 않음 |  |

| resolution | VARCHAR(30) | `pending` / `user\_reexplained` / `user\_flagged\_wrong` / `skipped` | 2차 |

| created\_at | TIMESTAMPTZ |  |  |



\*\*1차엔 테이블만 만들고 행은 안 생겨.\*\* `document\_claims.repository\_hint`가 2차에 채워져야 대조가 성립하니까. 미리 만드는 이유는 FK가 양쪽(`document\_claims`, `evidences`)을 참조해서, 나중에 추가하면 정합성을 다시 봐야 하기 때문이야.



\---



\### 전체 흐름 요약



```

M4-a  interview\_sessions INSERT (status='preparing', context\_state 초기화)

&#x20;     session\_repositories 확정 → L2 deep



T1    evidences INSERT (tool\_name=NULL 또는 Tool 호출)

&#x20;     interview\_turns INSERT (status='asked', depth, jd\_requirement\_ids, claim\_ids)

&#x20;     turn\_evidences INSERT (usage='question\_basis')



T2    interview\_turns UPDATE (answer\_text, status='answered')   ← 제출 1회



T3    interview\_turns UPDATE (analysis)



T4    interview\_turns UPDATE (decision)

&#x20;     interview\_sessions UPDATE (context\_state, turn\_count, elapsed\_sec)

&#x20;     → max\_turns 도달? 아니면 T1로 회귀



M4-end interview\_sessions UPDATE (status='completed' | 'abandoned', abandoned\_at\_turn)



M6    interview\_reports / report\_scores INSERT

&#x20;     turn\_evidences INSERT (usage='evaluation\_basis')

```



\---



\### 1차 / 2차 경계



| 항목 | 1차 | 2차 |

| --- | --- | --- |

| `interview\_sessions` | ✅ `answer\_mode='text'` 고정 | `voice` 추가, `paused` 상태 |

| `interview\_turns` | ✅ `topic\_code` FK 없음 | FK 추가, `analysis`/`decision` 테이블 승격 |

| `evidences` | ✅ 전체 | 세션 간 캐시(선택) |

| `turn\_evidences` | ✅ 전체 | — |

| `evidence\_conflicts` | ⏸ \*\*빈 테이블\*\* | ✅ 행 생성 |

| `tool\_calls` | ⏸ 없음 | ✅ Tool 계약 확정 후 |

| 답변 초안 저장 | ❌ 미지원 (확정) | 검토 |

| 세션 재개 | ❌ 미지원 (확정) | 검토 |



\---



\### 의논할 사항 : 남은 값 3개



스키마는 다 확정됐고, \*\*값만 정하면 돼:\*\*



| 항목 | 컬럼 | 참고 |

| --- | --- | --- |

| 질문 개수 | `max\_turns` | 6,2,1 느낌으로  |

| 면접 시간 | `planned\_duration\_sec` | 9턴 × 텍스트 2분 ≈ \*\*20분(1200초)\*\* |

| `timeout` 판정 | — | 서버 배치 없으면 이탈 턴이 `asked`로 영구 잔류. \*\*1차엔 `timeout` 미사용\*\*하고 `asked`+`abandoned\_at\_turn`으로 갈음해도 됨 |



세 번째는 \*\*`timeout` 값을 1차에 안 쓰는 것\*\*을 권장해. 배치 작업 하나를 안 만들어도 되고, 이탈 지점은 `abandoned\_at\_turn`으로 이미 잡히니까.



\## 6. 리포트

아직 안만들어짐.

