"""6개 루브릭 시드 (label_ko 포함).

docs/task-03-seed.md / spec/ai/features/answer-evaluation.md

score_key 6종은 spec/ai/features/answer-evaluation.md · spec/backend/features/report.md 가
이미 고정한 값이다 (바꿀 수 없음). totalScore는 이 6개의 단순 평균이고 weight는 없다.

⚠ 6개 전부 항상 0~100 숫자를 낸다. 근거(JD·자소서)가 부족한 경우도 NULL이 아니라 앵커의
낮은 점수 쪽으로 흡수한다.

⚠ db/models/knowledge.py 의 ScoreCriteria 모델이 아직 없다 (task-02 선행). 모델이 생기면
이 데이터를 그대로 INSERT/upsert 하는 함수를 여기 추가한다.
"""

from __future__ import annotations

SCORE_CRITERIA_SEED: list[dict] = [
    {
        "score_key": "project_understanding",
        "label": "프로젝트 이해도",
        "rubric": {
            "1": "레포의 구조나 사용 기술을 스스로 설명하지 못하거나 질문과 무관한 답변을 한다.",
            "3": "주요 컴포넌트·기술 스택은 설명하지만, 왜 그런 구조를 선택했는지 근거를 대지 못한다.",
            "5": "아키텍처 결정 배경과 트레이드오프까지 구체적 근거를 들어 설명한다.",
        },
    },
    {
        "score_key": "technical_reasoning",
        "label": "기술적 사고력",
        "rubric": {
            "1": "기술적 판단의 근거를 전혀 제시하지 못하거나 사실과 다른 설명을 한다.",
            "3": "선택한 기술/방법은 설명하지만 대안과의 비교나 한계는 언급하지 못한다.",
            "5": "대안을 비교하고 트레이드오프·한계를 스스로 인식하며 논리적으로 설명한다.",
        },
    },
    {
        "score_key": "problem_solving",
        "label": "문제 해결력",
        "rubric": {
            "1": "문제 상황이나 해결 과정을 설명하지 못한다.",
            "3": "문제와 해결 방법은 설명하지만 왜 그 방법을 택했는지 과정이 불명확하다.",
            "5": "문제 정의부터 원인 분석, 해결 과정, 결과 검증까지 논리적으로 설명한다.",
        },
    },
    {
        "score_key": "communication",
        "label": "커뮤니케이션",
        "rubric": {
            "1": "질문의 의도와 무관하거나 이해하기 어려운 답변을 한다.",
            "3": "질문에 맞는 답변이지만 장황하거나 핵심이 흐릿하다.",
            "5": "질문 의도에 맞춰 핵심을 먼저 말하고 근거를 간결하게 덧붙인다.",
        },
    },
    {
        # 근거: 답변 중 기여 관련 진술 + answer_vs_code 대조. 자소서 claim 추출은 Sprint 1에 없다
        # (document_claims는 Sprint 1에 row를 만들지 않는다) — 자료 부족은 낮은 점수로 흡수한다.
        "score_key": "contribution_clarity",
        "label": "기여도 명확성",
        "rubric": {
            "1": "본인 기여와 타인/팀 기여를 구분하지 못하거나, 근거 없이 기여를 주장한다.",
            "3": "본인 기여를 언급하지만 구체적 범위(무엇을 직접 했는지)가 모호하다.",
            "5": "본인이 직접 수행한 부분을 근거와 함께 구체적 범위로 명확히 구분해 설명한다.",
        },
    },
    {
        # 근거: domain_lead 의 domain question frame(업종별 개인정보/장애·운영/UX 축).
        # jd_requirements 문구 대조가 아니라 도메인 맥락 연결 여부를 본다.
        "score_key": "company_job_fit",
        "label": "기업·직무 적합성",
        "rubric": {
            "1": "지원 도메인(업종)과 무관하거나 모순되는 답변을 한다.",
            "3": "도메인 맥락은 인지하지만 본인 경험과 구체적으로 연결하지 못한다.",
            "5": "지원 도메인 특성(개인정보·장애/운영·사용자 경험 맥락 등)을 본인 프로젝트 경험과 구체적으로 연결해 설명한다.",
        },
    },
]
