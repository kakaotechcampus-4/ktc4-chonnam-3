import pytest

from app.features.interview.turn_position import turn_position


def test_turns_without_follow_ups_are_each_a_main_question():
    turns = [(1, 1), (2, 1), (3, 1)]

    assert [turn_position(turns, n) for n in (1, 2, 3)] == [(1, 0), (2, 0), (3, 0)]


def test_follow_up_belongs_to_its_main_question_and_carries_its_depth():
    turns = [(1, 1), (2, 1), (3, 2), (4, 3), (5, 1)]

    assert [turn_position(turns, n) for n in (1, 2, 3, 4, 5)] == [
        (1, 0),
        (2, 0),
        (2, 1),
        (2, 2),
        (3, 0),
    ]


@pytest.mark.parametrize("depth", [0, -1])
def test_non_positive_depth_is_treated_as_a_main_question(depth):
    assert turn_position([(1, depth)], 1) == (1, 0)


def test_unknown_turn_defaults_without_inventing_a_follow_up():
    assert turn_position([(1, 1)], 2) == (1, 0)
