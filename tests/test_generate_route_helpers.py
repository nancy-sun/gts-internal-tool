from starlette.datastructures import FormData

from app.routes.generate import parse_selected_candidates


def test_parse_selected_candidates_includes_checked_rows():
    form = FormData(
        [
            ("include__4", "1"),
            ("candidate__4", "10"),
            ("include__5", "1"),
            ("candidate__5", "20"),
        ]
    )

    assert parse_selected_candidates(form) == {4: 10, 5: 20}


def test_parse_selected_candidates_skips_unchecked_rows():
    form = FormData(
        [
            ("include__4", "1"),
            ("candidate__4", "10"),
            ("candidate__5", "20"),
        ]
    )

    assert parse_selected_candidates(form) == {4: 10}
