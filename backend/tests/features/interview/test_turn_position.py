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


def test_nonadjacent_follow_up_uses_its_parent_root_and_chain_depth():
    turns = [(1, 1, None), (2, 1, None), (3, 1, None), (4, 2, 2), (5, 1, None), (6, 3, 4)]

    assert turn_position(turns, 4) == (2, 1)
    assert turn_position(iter(turns), 6) == (2, 2)


def test_legacy_follow_up_without_parent_retains_stored_depth_and_nearest_main():
    turns = [(1, 1, None), (2, 1, None), (3, 2, None), (4, 3, None)]

    assert turn_position(turns, 4) == (2, 2)
