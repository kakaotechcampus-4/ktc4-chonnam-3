"""기능 계층에 의존하지 않는 JSONB 원문 문자열 검사."""


def validate_storage_strings(value: object) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str) and "\x00" in current:
            raise ValueError("Invalid JSON storage character")
        if isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
