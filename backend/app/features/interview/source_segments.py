"""언어와 무관한 텍스트 구간화. 원문을 재작성하지 않고 실제 줄 위치를 보존한다."""

from devon_ai import contracts as c


def segment_text(
    path: str,
    text: str,
    *,
    max_segment_bytes: int,
    total_bytes: int,
    overlap_lines: int = 2,
    max_segments: int = 16,
) -> tuple[tuple[c.SourceDocument, ...], tuple[str, ...]]:
    if max_segment_bytes < 1 or total_bytes < 0 or overlap_lines < 0 or max_segments < 1:
        raise ValueError("invalid source segment budget")
    if not text.strip():
        return (), (f"빈 파일은 분석 원문에서 제외했습니다: {path}",)
    size = len(text.encode("utf-8"))
    if size <= min(max_segment_bytes, total_bytes):
        return (c.SourceDocument(path, "file", text, "entire file"),), ()

    lines = text.splitlines(keepends=True)
    sizes = [len(line.encode("utf-8")) for line in lines]
    segments: list[c.SourceDocument] = []
    limitations: list[str] = []
    cursor = 0
    remaining = total_bytes
    while cursor < len(lines) and remaining and len(segments) < max_segments:
        # 한 줄을 중간에서 자르면 위치 계약이 거짓이 되므로 해당 줄은 미확인으로 남긴다.
        if sizes[cursor] > max_segment_bytes:
            limitations.append(f"한 줄 크기 상한으로 읽지 못한 원문: {path}:{cursor + 1}")
            cursor += 1
            continue
        start, used = cursor, 0
        while cursor < len(lines) and used + sizes[cursor] <= min(max_segment_bytes, remaining):
            used += sizes[cursor]
            cursor += 1
        if cursor == start:
            break
        scope = f"lines {start + 1}-{cursor}"
        content = "".join(lines[start:cursor])
        # 겹침 꼬리나 선행 공백만 남아도 유효한 다른 구간까지 버리지 않는다.
        # 원문을 strip해 위치를 바꾸지 않고, 제외한 실제 줄 범위만 한계로 남긴다.
        if content.strip():
            segments.append(c.SourceDocument(path, "file", content, scope, start + 1, cursor))
        else:
            limitations.append(
                f"공백 구간은 분석 원문에서 제외했습니다: {path}:{start + 1}-{cursor}"
            )
        remaining -= used
        if cursor < len(lines) and overlap_lines:
            # 최소 한 줄은 앞으로 진행해야 겹침만 반복하는 무한 루프가 생기지 않는다.
            cursor = max(start + 1, cursor - overlap_lines)
    covered_end = max((item.end_line or 0 for item in segments), default=0)
    if covered_end < len(lines):
        limitations.append(
            f"분석 원문 예산으로 확인하지 못한 범위: {path}:{covered_end + 1}-{len(lines)}"
        )
    return tuple(segments), tuple(limitations)
