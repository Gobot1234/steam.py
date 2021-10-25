from dataclasses import dataclass
from typing import List

import betterproto

from .base import CClanEventData


@dataclass(eq=False, repr=False)
class RespondToClanInviteRequest(betterproto.Message):
    steamid: int = betterproto.fixed64_field(1)
    accept: bool = betterproto.bool_field(2)


@dataclass(eq=False, repr=False)
class RespondToClanInviteResponse(betterproto.Message):
    pass


# not public and also non-functional atm
@dataclass(eq=False, repr=False)
class GetAdjacentPartnerEventsRequest(betterproto.Message):
    steam_id: int = betterproto.fixed64_field(1)  # might be account id
    announcement_id: int = betterproto.fixed64_field(2)
    # count_later: int = betterproto.uint32_field(2)  # might allow announcement_id
    # might allow the limit


@dataclass(eq=False, repr=False)
class GetAdjacentPartnerEventsResponse(betterproto.Message):
    events: List[CClanEventData] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class GetEventDetailsRequest(betterproto.Message):
    event_ids: List[int] = betterproto.int64_field(1)
    clan_ids: List[int] = betterproto.fixed32_field(2)


@dataclass(eq=False, repr=False)
class GetEventDetailsResponse(betterproto.Message):
    events: List[CClanEventData] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class GetSinglePartnerEventRequest(betterproto.Message):
    clan_id: int = betterproto.fixed32_field(1)
    announcement_id: int = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class GetSinglePartnerEventResponse(betterproto.Message):
    events: List[CClanEventData] = betterproto.message_field(1)
