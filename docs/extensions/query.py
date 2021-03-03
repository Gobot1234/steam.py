# -*- coding: utf-8 -*-

# If you are wondering why this is done, it enables metaclass attributes to be picked up as class attributes/properties
# AFAIK there is no good way to do this apart from just recreating the class.

import inspect

import steam
from steam.game_server import Query, QueryMeta


def setup(_):

    attrs = dict(inspect.getmembers(QueryMeta, predicate=lambda attr: isinstance(attr, property)))
    attrs.update({"query": Query.query, "all": Query.all})

    steam.Query = steam.game_server.Query = type(
        "Query",
        (),
        attrs,
    )
