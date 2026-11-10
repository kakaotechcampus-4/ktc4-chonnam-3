"""저장된 부모 관계를 따라 메인 질문 번호와 꼬리질문 깊이를 계산한다."""

from collections.abc import Iterable

type TurnPosition = tuple[int, int, int | None]


def turn_position(turns: Iterable[TurnPosition | tuple[int, int]], turn_no: int) -> tuple[int, int]:
    """`(turn_no, depth, parent_turn_no)`에서 `(mainIndex, followUpDepth)`를 구한다.

    부모가 없던 기존 레코드와 두 필드 입력은 이전 depth 기반 표시를 보존한다.
    명시된 부모가 잘못된 경우에는 가까운 메인을 임의 부모로 대신하지 않는다.
    """
    rows = {item[0]: (item[1], item[2] if len(item) == 3 else None) for item in turns}
    root, followed = turn_no, 0
    while root in rows:
        depth, parent = rows[root]
        if parent is None:
            # 관계 필드 도입 전 저장한 꼬리질문은 기존 depth를 그대로 표시한다.
            followed += max(depth - 1, 0)
            break
        if parent not in rows or not 1 <= parent < root:
            raise ValueError("question_parent_invalid")
        root, followed = parent, followed + 1
    mains = sum(1 for number, (depth, _) in rows.items() if number <= root and depth <= 1)
    return max(mains, 1), followed
