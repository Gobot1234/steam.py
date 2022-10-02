import betterproto

from .base import CClanEventData
from .msg import UnifiedMessage


class RespondToClanInviteRequest(UnifiedMessage, um_name="Clan.RespondToClanInvite"):
    steamid: int = betterproto.fixed64_field(1)
    accept: bool = betterproto.bool_field(2)


class RespondToClanInviteResponse(UnifiedMessage, um_name="Clan.RespondToClanInvite"):
    pass


# not public and also non-functional atm


class GetAdjacentPartnerEventsRequest(UnifiedMessage, um_name="Clan.GetAdjacentPartnerEvents"):
    steam_id: int = betterproto.fixed64_field(1)  # might be account id
    announcement_id: int = betterproto.fixed64_field(2)
    # count_later: int = betterproto.uint32_field(2)  # might allow announcement_id
    # might allow the limit


class GetAdjacentPartnerEventsResponse(UnifiedMessage, um_name="Clan.GetAdjacentPartnerEvents"):
    events: list[CClanEventData] = betterproto.message_field(1)


class GetEventDetailsRequest(UnifiedMessage, um_name="Clan.GetEventDetails"):
    event_ids: list[int] = betterproto.fixed64_field(1)
    clan_ids: list[int] = betterproto.fixed32_field(2)


class GetEventDetailsResponse(UnifiedMessage, um_name="Clan.GetEventDetails"):
    events: list[CClanEventData] = betterproto.message_field(1)


class GetSinglePartnerEventRequest(UnifiedMessage, um_name="Clan.GetSinglePartnerEvent"):
    clan_id: int = betterproto.fixed32_field(1)
    announcement_id: int = betterproto.uint64_field(2)


class GetSinglePartnerEventResponse(UnifiedMessage, um_name="Clan.GetSinglePartnerEvent"):
    events: list[CClanEventData] = betterproto.message_field(1)
