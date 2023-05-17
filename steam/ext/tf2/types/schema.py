from __future__ import annotations

from typing import Any, Literal

from multidict import MultiDict
from typing_extensions import Literal, NotRequired, TypedDict

from ....types.vdf import VDFBool


class ValueDict(TypedDict, MultiDict):  # type: ignore
    value: int


class ColorDict(TypedDict, MultiDict):  # type: ignore  # I'm sorry my fellow tea drinkers
    color_name: str


class RaritiesDict(TypedDict, MultiDict):  # type: ignore
    value: int
    loc_key: str
    loc_key_weapon: str
    color: str
    next_rarity: NotRequired[str]


class EquipConflicts(TypedDict, MultiDict):  # type: ignore
    glasses: MultiDict[int]
    whole_head: MultiDict[int]


class CollectionDict(TypedDict, MultiDict):  # type: ignore
    name: str
    description: str
    is_reference_collection: VDFBool
    items: MultiDict[int]


class OperationInfo(TypedDict, MultiDict):  # type: ignore
    name: str
    gateway_item_name: str
    required_item_name: str
    operation_start_date: str  # format of "2017-10-15 00:00:00" and "2038-01-01 00:00:00"
    stop_adding_to_queue_date: str
    stop_giving_to_player_date: str
    contracts_end_date: str  # all datetimes with above format
    quest_log_res_file: NotRequired[str]
    quest_list_res_file: NotRequired[str]
    operation_lootlist: str
    is_campaign: VDFBool
    max_drop_count: NotRequired[int]


class ItemInfo(TypedDict, MultiDict):  # type: ignore
    name: str
    prefab: str
    item_name: str
    item_description: str
    image_inventory: str


class AttributeInfo(TypedDict, MultiDict):  # type: ignore
    name: str
    attribute_class: str
    description_string: NotRequired[str]
    description_format: str
    hidden: VDFBool
    effect_type: Literal["positive", "neutral", "negative"]
    stored_as_integer: VDFBool
    armory_desc: NotRequired[str]


class ItemSet(TypedDict, MultiDict):  # type: ignore
    name: str
    items: MultiDict[Literal["1"]]
    attributes: MultiDict[MultiDict[str]]
    store_bundle: NotRequired[str]


class CraftInfo(TypedDict, MultiDict):  # type: ignore
    name: str
    n_A: str
    desc_inputs: str
    desc_outputs: str
    di_A: str
    di_B: str
    do_A: str
    do_B: str
    all_same_class: NotRequired[VDFBool]
    always_known: VDFBool
    premium_only: VDFBool
    disabled: VDFBool
    input_items: MultiDict[MultiDict[CraftInfoIOItem]]
    output_items: MultiDict[MultiDict[CraftInfoIOItem]]


class CraftInfoIOItem(TypedDict, MultiDict):  # type: ignore
    field: str
    operator: str
    value: str
    required: VDFBool


class Schema(TypedDict, MultiDict):  # type: ignore
    game_info: MultiDict[int]
    qualities: MultiDict[ValueDict]
    colors: MultiDict[ColorDict]
    rarities: MultiDict[RaritiesDict]
    equip_regions_list: MultiDict[VDFBool | dict[Literal["shared"], VDFBool]]
    equip_conflicts: MultiDict[MultiDict[VDFBool]]
    quest_objective_conditions: MultiDict[Any]  # this is not really possible to type
    item_series_types: MultiDict[MultiDict[Any]]
    item_collections: MultiDict[CollectionDict]
    operations: MultiDict[OperationInfo]
    prefabs: MultiDict[MultiDict[Any]]  # there are too many options for this for me to type them for now TODO
    items: MultiDict[ItemInfo]
    attributes: MultiDict[AttributeInfo]
    item_criteria_templates: MultiDict[MultiDict[str]]
    random_attribute_templates: MultiDict[MultiDict[str]]
    lootlist_job_template_definitions: MultiDict[MultiDict[str]]
    item_sets: MultiDict[ItemSet]
    client_loot_lists: MultiDict[str | MultiDict[Literal["1"]]]
    revolving_loot_lists: MultiDict[str]
    recipes: MultiDict[CraftInfo]
    achievement_rewards: MultiDict[str | MultiDict[str | MultiDict[str]]]
