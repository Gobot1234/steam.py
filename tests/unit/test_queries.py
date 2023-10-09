import pytest

import steam
from steam import Query


@pytest.mark.parametrize(
    "query, raw_query",
    [
        (Query.where(app=steam.TF2, empty=False, secure=True), r"\app\440\empty\1\secure\1"),
        (Query.where(empty=False, app=steam.TF2), r"\empty\1\app\440"),
        (Query.where(version_match="*"), r"\version_match\*"),
        (Query.where(is_proxy=False), r"\nor\1\proxy\1"),
        (
            steam.Query.where(name_match="A cool server*", tags=["all_talk", "sv_cheats"]),
            r"\name_match\A cool server*\gametype\all_talk,sv_cheats",
        ),
    ],
)
def test_query_generation(query: str, raw_query: str) -> None:
    assert query == raw_query
