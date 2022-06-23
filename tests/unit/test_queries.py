import pytest

import steam
from steam import Query


@pytest.mark.parametrize(
    "query, raw_query",
    [
        (Query.running / steam.TF2 / Query.not_empty / Query.secure, r"\appid\440\empty\1\secure\1"),
        (Query.not_empty & Query.secure, r"\nand\[\empty\1\secure\1]"),
        (steam.Query.not_empty / steam.Query.running / steam.TF2, r"\empty\1\appid\440"),
        (steam.Query.version_match / "*", r"\version_match\*"),
        (steam.Query.not_empty / steam.Query.not_full | steam.Query.secure, r"\nor\[\empty\1\full\1\secure\1]"),
        (
            steam.Query.name_match / "A cool server" | steam.Query.match_tags / ["all_talk", "sv_cheats"],
            r"\nor\[\name_match\A cool server\gametype\[all_talk,sv_cheats]]",
        ),
    ],
)
def test_query_generation(query: Query, raw_query: str) -> None:
    assert query.query == raw_query
