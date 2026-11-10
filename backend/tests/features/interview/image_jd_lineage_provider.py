"""합성 Wanted·GitHub·모델 응답만 제어하며 실제 외부 사이트 호출로 해석하지 않는다."""

import json
from dataclasses import asdict

import httpx

from app.integrations.vision.elice import VisionBlock, VisionResult
from tests.agents.director_helpers import analysis, approved_review, plan, response
from tests.agents.test_director_prepare import Transport

URL = "https://www.wanted.co.kr/wd/987654321"
IMAGE = "https://static.wanted.co.kr/fixture-lineage.png"
USED = "Python 개발 경험"
UNUSED = "Redis 운영 경험"
LIMIT = "fixture_partial_transcription"
ANSWER = "팀원 담당입니다"


class ImageLineageProvider:
    """요구사항·모델 요청의 관찰을 외부 응답 경계에서만 기록한다."""

    def __init__(self, *, excerpt=False):
        self.excerpt = excerpt
        self.revision = 1
        self.vision_calls = 0
        self.requests = []
        self.posting_calls = 0
        self.github = None

    @property
    def used_text(self):
        return USED if self.revision == 1 else "변경된 Python 개발 경험"

    async def extract(self, *args, **kwargs):
        self.vision_calls += 1
        suffix = "\n" + "확인한 원문 " * 1000 if self.excerpt else ""
        return VisionResult(
            f"synthetic-vision-{self.vision_calls}",
            (
                VisionBlock(1, 0, "text", "우대사항\n" + self.used_text + suffix, "", [0, 0, 5, 5]),
                VisionBlock(1, 1, "text", "우대사항\n" + UNUSED, "", [0, 5, 5, 10]),
            ),
            1,
            {"fixture": "synthetic Wanted-shaped transport, not a live posting"},
        )

    def _plan(self, payload):
        context = payload["context"]
        persona = context["allowed_personas"][0]
        candidate = plan(persona)
        number = context["turn_no"]
        question = candidate["question"]
        question["text"] = f"{number}번 질문: 본인의 역할과 접근 방법을 설명해 주세요."
        question["topic_code"] = f"lineage_{number}"
        target = next(item for item in context["evaluation_targets"] if item["persona"] == persona)
        question["question_contract"]["evaluation_keys"] = target["keys"]
        if number == 2 or "company_job_fit" in target["keys"]:
            requirement = next(item for item in context["jd_requirements"] if item["text"] == USED)
            question["jd_requirement_ids"] = [requirement["id"]]
            question["question_contract"]["basis_refs"] = [
                {"kind": "jd_requirement", "id": requirement["id"]}
            ]
            question["text"] = f"{number}번 질문: 공고의 Python 요구사항과 역할을 연결해 주세요."
        if number == 3:
            evidence_id = context["evidence"][0]["evidence_id"]
            question["evidence_refs"] = [evidence_id]
            question["question_contract"]["basis_refs"] = [
                *question["question_contract"]["basis_refs"],
                {"kind": "evidence", "id": evidence_id},
            ]
        return candidate

    @staticmethod
    def _narrative(payload):
        def claim(text, turn_id="2"):
            return {"text": text, "turn_refs": [turn_id], "evidence_refs": []}

        return {
            "headline": "합성 입력의 이미지 JD 전달을 확인했습니다",
            "summary": {
                key: [claim("질문한 Python 요구사항을 기준으로 답변을 관찰했습니다.")]
                for key in ("strengths", "gaps", "follow_ups", "practice_actions")
            },
            "persona_feedbacks": [
                {
                    "persona": persona,
                    "tags": ["합성 회귀"],
                    "strengths": [claim("답변에서 설명한 역할을 관찰했습니다.", turn_id)],
                    "improvements": [claim("가정과 실제 경험을 구분해 보세요.", turn_id)],
                    "practice_actions": [claim("답변을 구체적인 사례로 정리해 보세요.", turn_id)],
                    "limitations": list(payload["limitations"]),
                }
                for persona in ("hr_manager", "tech_lead", "domain_lead")
                for turn_id in [
                    next(t["turn_id"] for t in payload["turns"] if t["persona"] == persona)
                ]
            ],
        }

    async def __call__(self, request):
        if request.method != "POST":
            if request.url.host == "www.wanted.co.kr":
                self.posting_calls += 1
                return httpx.Response(
                    200, json={"job": {"detail": {"position": "개발자", "image_urls": [IMAGE]}}}
                )
            if request.url.host == "static.wanted.co.kr":
                return httpx.Response(
                    200,
                    content=b"\x89PNG\r\n\x1a\nfixture" + str(self.revision).encode(),
                    headers={"Content-Type": "image/png"},
                )
            assert self.github is not None
            return await self.github(request)
        envelope = json.loads(request.content)
        payload = json.loads(envelope["input"][0]["content"][0]["text"])
        self.requests.append(payload)
        if "blocks" in payload:
            return response(
                {
                    "requirements": [
                        {
                            "category": "preferred",
                            "text": self.used_text,
                            "tech_tags": ["Python"],
                            "source_ids": ["I0-P1-E0"],
                        },
                        {
                            "category": "preferred",
                            "text": UNUSED,
                            "tech_tags": ["Redis"],
                            "source_ids": ["I0-P1-E1"],
                        },
                    ],
                    "limitations": [LIMIT],
                }
            )
        if payload.get("operation") == "plan":
            return response(self._plan(payload))
        if payload.get("operation") == "review":
            return response(approved_review())
        if "answer" in payload:
            return response(asdict(analysis()))
        if "rubric" in payload:
            return response(
                {
                    "judgments": [
                        {"turn_id": turn["turn_id"], "key": key, "level": 3}
                        for turn in payload["turns"]
                        for key in turn["candidate_keys"]
                    ]
                }
            )
        if "turns" in payload:
            return response(self._narrative(payload))
        raise AssertionError("예상하지 않은 공급자 요청입니다")

    def bind_repository(self, seed):
        self.github = Transport(seed)
