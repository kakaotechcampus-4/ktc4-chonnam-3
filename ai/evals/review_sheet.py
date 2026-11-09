"""Render a one-page reviewer sheet per eval case. Not part of the runtime package.

Usage (run in ai/): uv run python evals/review_sheet.py [case_id ...]
Sheet file name: {case_id}.v{version}.md, so versions of one case do not overwrite each other.
Sheets contain the answer key, so they go to the ignored ai/report/ folder, never to a model.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from eval_cases import Case, CaseError, _history, load_cases
from grader_check import EXPECTED

_VERDICT = {"accept": "통과", "reject": "거부", "ambiguous": "판정 보류"}
_FACT_ROWS = ("사실", "확인 범위", "미확인", "확인 수준", "금지", "사례 가공", "출처")

_SHARED = (
    "모델이 받는 입력에서 정답 기준과 다르게 해석할 여지가 없는가?",
    "채점기 시험용 가짜 답의 종류가 맞는가?",
)
_QUESTIONS = {
    "evidence": (
        "통과 항목이 원본 사실의 '확인 범위'를 넘지 않는가? (원본보다 넓지 않은가)",
        "실패 항목은 모두 원본 사실의 '미확인'에서 나온 넘겨짚기인가? 빠진 넘겨짚기는 없는가?",
        *_SHARED,
    ),
    "report": (
        "통과 항목은 입력 대화와 근거에 맞는 리포트 서술인가? 근거 없는 단정을 허용하지 않는가?",
        "실패 항목은 모두 입력 대화나 근거에 어긋나는 서술인가? 빠진 실패 서술은 없는가?",
        *_SHARED,
    ),
    "report_pair": (
        "강한 사례의 답변이 약한 사례보다 비교 key에서 분명히 더 좋은가?",
        "달라진 답변이 비교 key 외의 다른 key 점수를 좌우하지 않게 쓰였는가?",
        "두 사례의 점수 차이가 `min_gap`의 두 배 이상 날 만큼 답변 차이가 충분한가?",
        "비교 key를 평가하는 질문이 이 면접 대화에 실제로 있는가? (없으면 점수가 비교되지 않는다)",
        *_SHARED,
    ),
    "interview": (
        "통과 항목은 아래 정책에 맞는 좋은 다음 행동인가? "
        "정책이 허용하지 않는 행동을 통과시키지 않는가?",
        "실패 항목은 모두 아래 정책이나 입력에 어긋나는 행동인가? 빠진 실패 행동은 없는가?",
        *_SHARED,
    ),
}

# Condensed from spec/ai/features/interviewer.md (the source of truth); update both together.
_POLICY = (
    "다음 질문의 Persona는 허용 목록 안에서만 고르고, 남은 할당이 없는 Persona는 쓰지 않는다.",
    "질문은 한 가지 중심 목적을 갖고, 복합 질문이나 정답 유도를 하지 않는다.",
    "이미 충분히 확인한 목적은 표현만 바꿔 반복하지 않는다. 보완 질문은 부족한 부분을, "
    "심화 질문은 새로운 판단 조건을 묻는다.",
    "읽지 않은 구현·성능·배포 성공을 사실로 단정하지 않는다. 검색에서 못 찾은 것을 거짓의 "
    "증거로 말하지 않고, 답변과 코드의 차이는 확인형 질문으로 한다.",
    "후보자의 개인 기여나 도메인 실무 경험을 추정하지 않는다. 후보자의 정정은 반영한다.",
    "전제가 거짓이거나 목적이 잘못된 후보는 표현 재작성이 아니라 재계획 대상이고, 안전한 질문을 "
    "만들 수 없으면 검증되지 않은 질문을 내지 않고 유효 후보 없음으로 답한다.",
    "정상 종료(finish)는 9번째 답변 처리를 마친 뒤에만 한다. 그 전의 조기 종료는 허용하지 않고, "
    "사용자가 종료를 요청한 뒤에는 질문을 이어 가지 않는다.",
)


def fact_record(fact_table: str, fact_id: str) -> dict[str, str]:
    """Rows of one `### F-… · title` table in fact-table.md, or CaseError if absent."""
    match = re.search(rf"^### {re.escape(fact_id)} .*?(?=^#{{2,3}} |^---)", fact_table, re.M | re.S)
    if not match:
        raise CaseError(f"{fact_id}: not found in fact-table.md")
    rows: dict[str, str] = {}
    for line in match.group(0).splitlines():
        if line.startswith("| ") and " | " in line and not line.startswith("| ---"):
            key, value = line[2:].rstrip(" |").split(" | ", 1)
            rows[key.strip()] = value.strip()
    return rows


def _table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    return out + ["| " + " | ".join(c.replace("|", "\\|") for c in r) + " |" for r in rows]


def _payload(payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key, value in payload.items():
        if key == "history":
            out.append("- **history**:")
            for t in value:
                out += [
                    f"  - turn {t['turn']} · `{t['persona']}`",
                    f"    - 질문: {t['question']}",
                    f"    - 답변: {t['answer']}",
                ]
        elif key != "materials":
            shown = value if isinstance(value, str | int) else json.dumps(value, ensure_ascii=False)
            out.append(f"- **{key}**: {shown}")
        else:
            for m in value:
                out += [
                    "",
                    f"**{m['ref']}** — `{m['path']}` ({m['lines']}줄)",
                    "",
                    "```",
                    m["text"],
                    "```",
                ]
    return out


def _comparison(case: Case, partner: Case) -> list[str]:
    pair = case.expectation["pair"]
    role = {"stronger": "강한 사례", "weaker": "약한 사례"}[pair["role"]]
    lines = [
        "## 비교 정보 (쌍 사례)",
        "",
        f"쌍 `{pair['pair_id']}` / 이 사례는 **{role}** / "
        f"상대 사례 `{partner.case_id}` v{partner.version} / 비교 key `{pair['key']}` / "
        f"최소 점수 차이 `min_gap` {pair['min_gap']}점",
        "",
        "질문·Persona·근거는 두 사례가 같고, 아래 답변만 다르다.",
        "",
    ]
    mine = {t["turn"]: t for t in _history(case, allow_legacy_report_contracts=True)}
    rows: list[tuple[str, ...]] = [
        (
            str(n),
            mine[n]["persona"],
            mine[n]["answer"] if mine[n]["answer"] is not None else "(미응답)",
            other["answer"] if other["answer"] is not None else "(미응답)",
        )
        for n, other in (
            (t["turn"], t) for t in _history(partner, allow_legacy_report_contracts=True)
        )
        if mine[n]["answer"] != other["answer"]
    ]
    return lines + _table(("turn", "Persona", "이 사례의 답변", "상대 사례의 답변"), rows) + [""]


def render_sheet(case: Case, fact: dict[str, str] | None, partner: Case | None = None) -> str:
    exp, review = case.expectation, case.expectation["review"]
    lines = [
        f"# 검수 시트 — {case.case_id} v{case.version}",
        "",
        f"종류 `{case.kind}` / 구분 `{case.split}` / 원본 그룹 `{case.source_group_id}` / "
        f"작성자 `{review['author']}` / 검수 상태 `{review['status']}`",
        "",
        "## ① 모델이 받는 것",
        "",
        *_payload(case.payload),
        "",
    ]
    interview = case.kind in ("question", "flow")
    if interview:
        lines += [
            "## ② 기준이 되는 면접 정책",
            "",
            *(f"{i}. {p}" for i, p in enumerate(_POLICY, 1)),
        ]
    elif fact is None:
        lines += ["## ② 원본 사실", "", "이 사례에는 원본 사실이 연결돼 있지 않습니다."]
    else:
        lines += ["## ② 원본 사실", ""]
        lines += _table(("항목", "내용"), [(k, fact[k]) for k in _FACT_ROWS if k in fact])
    if partner is not None:
        lines += ["", *_comparison(case, partner)]
    lines += ["", "## ③ 정답 기준 (작성자가 정함)", ""]
    lines += _table(("통과(허용)", "내용"), [(a["id"], a["purpose"]) for a in exp["allowed"]])
    lines += [""]
    lines += _table(
        ("실패(금지)", "내용", "유형"),
        [(f["id"], f["reason"], f["type"]) for f in exp["forbidden"]],
    )
    lines += ["", "## ④ 채점기 시험용 가짜 답", ""]
    lines += _table(
        ("종류", "가짜 답", "채점기가 내야 할 판정"),
        [(g["kind"], g["output"], _VERDICT[EXPECTED[g["kind"]]]) for g in exp["grader_controls"]],
    )
    if interview:
        kind = "interview"
    elif case.kind == "report":
        kind = "report_pair" if partner is not None else "report"
    else:
        kind = "evidence"
    lines += ["", "## 판단할 것", ""]
    lines += _table(
        ("#", "질문", "판정"),
        [(str(i), q, "□ 맞음 □ 수정 필요 □ 모름") for i, q in enumerate(_QUESTIONS[kind], 1)],
    )
    lines += [
        "",
        "## 결과 전달",
        "",
        f"사례 번호와 판정만 적어 주세요. 예: `{case.case_id} 통과` 또는 "
        f"`{case.case_id} 수정요청 - 2번, 사유 ...`",
        "",
    ]
    return "\n".join(lines)


def main(root: Path, out_dir: Path, only: list[str]) -> list[Path]:
    fact_text = (root / "expectations" / "fact-table.md").read_text(encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    cases = load_cases(root, allow_legacy_report_contracts=True)
    by_pair: dict[str, list[Case]] = {}
    for case in cases:
        if "pair" in case.expectation:
            by_pair.setdefault(case.expectation["pair"]["pair_id"], []).append(case)
    for case in cases:
        if only and case.case_id not in only:
            continue
        fact_id = case.expectation.get("source_fact")
        partners = [
            c
            for c in by_pair.get(case.expectation.get("pair", {}).get("pair_id"), [])
            if c is not case
        ]
        sheet = render_sheet(
            case,
            fact_record(fact_text, fact_id) if fact_id else None,
            partners[0] if partners else None,
        )
        path = out_dir / f"{case.case_id}.v{case.version}.md"
        path.write_text(sheet, encoding="utf-8", newline="\n")
        written.append(path)
    return written


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    for p in main(here, here.parent / "report" / "review-sheets", sys.argv[1:]):
        sys.stdout.write(f"{p}\n")
