"""질문이 몇 번째 메인 질문의 몇 번째 꼬리질문인지 DB의 `depth`에서 계산한다.

`depth`는 1이 주제 시작(메인), 2 이상이 꼬리질문이다. 값은 AI가 질문을 확정할 때 채우며
여기서는 새로 만들지 않고 저장된 값만 옮긴다. 아직 채우지 않은 턴은 전부 메인(depth 1)이다.
"""

from collections.abc import Iterable


def turn_position(turns: Iterable[tuple[int, int]], turn_no: int) -> tuple[int, int]:
    """`(turn_no, depth)` 목록과 대상 턴에서 `(mainIndex, followUpDepth)`를 돌려준다.

    mainIndex는 대상 턴까지 시작된 메인 질문 수(1부터)다. 꼬리질문은 속한 메인 질문의 번호를 갖는다.
    """
    mains = sum(1 for number, depth in turns if number <= turn_no and depth <= 1)
    depth = next((depth for number, depth in turns if number == turn_no), 1)
    return max(mains, 1), max(depth - 1, 0)
