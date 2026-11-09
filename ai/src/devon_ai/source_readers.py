"""구문 해석이 가능한 원문에 보조 구조를 제공하며 코드를 실행하지 않는다."""

import ast
import json
import tomllib
from pathlib import PurePosixPath

from devon_ai import contracts as c


def describe_source(source: c.SourceDocument) -> dict[str, object]:
    result: dict[str, object] = {
        "path": source.path,
        "scope": source.read_scope,
        "reader": "raw_text",
        "limitations": ["전용 구문 해석 없이 제공된 원문 구간만 분석합니다."],
    }
    # 부분 구간은 파일 문법의 완결성을 보장하지 않는다. 독립된 전체 파일처럼 파싱하지 않는다.
    if source.kind != "file" or source.read_scope != "entire file":
        return result
    suffix = PurePosixPath(source.path).suffix.lower()
    try:
        if suffix in {".json", ".toml"}:
            parsed = (
                json.loads(source.content) if suffix == ".json" else tomllib.loads(source.content)
            )
            result.update(
                reader=suffix[1:],
                top_level_keys=list(parsed)[:40] if isinstance(parsed, dict) else [],
                limitations=[
                    "구문과 최상위 구조만 확인했으며 설정의 실행 효과는 검증하지 않았습니다."
                ],
            )
        elif suffix == ".py":
            tree = ast.parse(source.content)
            symbols = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append(
                        {
                            "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                            "name": node.name,
                            "start_line": node.lineno,
                            "end_line": node.end_lineno,
                        }
                    )
                    if len(symbols) == 100:
                        break
            result.update(
                reader="python_ast",
                symbols=symbols,
                limitations=[
                    "정적 구문 구조만 확인했으며 동적 호출·실행 결과는 검증하지 않았습니다."
                ],
            )
    except (ValueError, SyntaxError, RecursionError, MemoryError):
        result["limitations"] = ["전용 해석기가 구문을 확인하지 못해 원문 구간으로 분석합니다."]
    return result
