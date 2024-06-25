"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from datetime import date, datetime
from http.cookies import SimpleCookie
from random import randbytes
from sys import version_info
from time import time
from typing import TYPE_CHECKING, Any, Literal, Mapping, TypeVar, Unpack, cast

import aiohttp
from bs4 import BeautifulSoup
from yarl import URL as URL_

from . import errors, utils
from .__metadata__ import __version__
from ._const import HTML_PARSER, JSON_DUMPS, JSON_LOADS, URL
from .enums import Currency, Language, Result, Type
from .id import CLAN_ID64_FROM_URL_REGEX, ID, parse_id64
from .models import PriceOverviewDict, api_route
from .types.id import ID32, ID64, AppID, AssetID, BundleID, ChatGroupID, ChatID, PackageID, PostID, TradeOfferID

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Iterable, Sequence, ValuesView

    from .client import Client, ClientKwargs
    from .media import Media
    from .types import achievement, app, bundle, clan, guard, trade, user
    from .types.http import AddWalletCode, CMList, Coro, EResultSuccess, ResponseDict, StrOrURL
    from .types.user import IndividualID
    from .user import ClientUser


T = TypeVar("T")
log = logging.getLogger(__name__)


async def json_or_text(r: aiohttp.ClientResponse, *, loads: Callable[[str], Any] = JSON_LOADS) -> Any:
    text = await r.text()
    try:
        if "application/json" in r.headers["Content-Type"]:
            return loads(text)
    except KeyError:
        pass
    return text


class HTTPClient:
    """The HTTP Client that interacts with the Steam web API."""

    def __init__(self, client: Client, **options: Unpack[ClientKwargs]):
        self._session: aiohttp.ClientSession = None  # type: ignore  # filled in login
        self.user: ClientUser = None  # type: ignore
        self._client = client

        self.api_key: str | None = None
        self.language: Language = options.get("language", Language.English)

        self.logged_in = False
        self.user_agent = (
            f"steam.py/{__version__} client (https://github.com/Gobot1234/steam.py), "
            f"Python/{version_info.major}.{version_info.minor}, aiohttp/{aiohttp.__version__}"
        )

        self.proxy: str | None = options.get("proxy")
        self.proxy_auth: aiohttp.BasicAuth | None = options.get("proxy_auth")
        self.connector: aiohttp.BaseConnector | None = options.get("connector")
        self.ssl = options.get("ssl")

    def clear(self) -> None:
        self._session = aiohttp.ClientSession(
            connector=self.connector,
            json_serialize=JSON_DUMPS,
        )

    async def request(
        self, method: str, url: StrOrURL, /, api_needs_auth: bool = True, **kwargs: Any
    ) -> Any:  # adapted from d.py
        kwargs["headers"] = {"User-Agent": self.user_agent, **kwargs.get("headers", {})}
        payload = kwargs.get("data")

        url = url if isinstance(url, URL_) else URL_(url)

        if url.host == URL.API.host:
            if api_needs_auth:
                kwargs["params"] |= (  # if valve ever decide to make this work, this'd be nice
                    # {"access_token": await self._client._state.ws.access_token()}
                    # if self._client._state.login_complete.is_set()
                    # else
                    {"key": await self.get_api_key()}
                )

        elif url.host in (URL.COMMUNITY.host, URL.STORE.host, URL.HELP.host):
            await self.ensure_logged_in()

        r = data = None
        for tries in range(5):
            async with self._session.request(
                method, url, **kwargs, proxy=self.proxy, proxy_auth=self.proxy_auth, ssl=self.ssl
            ) as r:
                log.debug("%s %s with PAYLOAD: %s has returned %d", method, r.url, payload, r.status)

                # even errors have text involved in them so this is safe to call
                data = await json_or_text(r)

                # the request was successful so just return the text/json
                if 200 <= r.status < 300:
                    log.debug("%s %s has received %s", method, r.url, data)
                    return data

                # we are being rate limited
                elif r.status == 429:
                    try:
                        # I haven't been able to get any X-Retry-After headers from the API, but we should probably still
                        # handle it
                        delay = float(r.headers["X-Retry-After"])
                    except KeyError:  # steam being un-helpful as usual
                        delay = 2**tries
                    log.warning("We are being rate limited sleeping for %s seconds", delay)
                    await asyncio.sleep(delay)
                    continue

                # we've received a 500 or 502, an unconditional retry
                elif r.status in {500, 502}:
                    await asyncio.sleep(1 + tries * 3)
                    continue

                elif r.status == 401:
                    if "key" in kwargs.get("params", ()) and (
                        isinstance(data, str)
                        and "Access is denied. Retrying will not help. Please verify your <pre>key=</pre>" in data
                    ):  # api key either got revoked or it was never valid, time to fetch a new key
                        key = await self.get_api_key()
                        assert key is not None
                        kwargs["params"]["key"] = key
                        continue  # retry with our new key
                    raise errors.HTTPException(r, data)

                # the usual error cases
                elif r.status == 403:
                    raise errors.Forbidden(r, data)
                elif r.status == 404:
                    raise errors.NotFound(r, data)
                else:
                    raise errors.HTTPException(r, data)

        assert r is not None
        # we've run out of retries, raise
        raise errors.HTTPException(r, data)

    def get(self, url: StrOrURL, **kwargs: Any) -> Coro[Any]:
        return self.request("GET", url, **kwargs)

    def post(self, url: StrOrURL, **kwargs: Any) -> Coro[Any]:
        return self.request("POST", url, **kwargs)

    async def get_cm_list(self, cell_id: int) -> CMList:
        params = {
            "cellid": cell_id,
            "cmtype": "websockets",
        }
        data: ResponseDict[CMList] = await self.get(
            api_route("ISteamDirectory/GetCMListForConnect"), api_needs_auth=False, params=params
        )
        return data["response"]

    def connect_to_cm(self, cm: str) -> Coro[aiohttp.ClientWebSocketResponse]:
        headers = {"User-Agent": self.user_agent}
        return self._session.ws_connect(  # type: ignore  # aiohttp types issue, fixed upstream
            f"wss://{cm}/cmsocket/", headers=headers, proxy=self.proxy, proxy_auth=self.proxy_auth
        )

    @utils.call_once(wait=True)
    async def login(self) -> None:
        jar = self._session.cookie_jar
        steam_login_secure = urllib.parse.quote(f"{self.user.id64}||{await self._client._state.ws.access_token()}")
        for url in (URL.COMMUNITY, URL.STORE, URL.HELP):
            jar.update_cookies(SimpleCookie(f"steamLoginSecure={steam_login_secure}"), url)
            jar.update_cookies(SimpleCookie(f"sessionid={self.session_id}"), url)
        self.logged_in = True

    async def ensure_logged_in(self) -> None:
        if self.logged_in:
            return
        await self._client._state.login_complete.wait()
        await self.login()

    @utils.call_once(wait=True)
    async def get_api_key(self) -> str | None:
        if self.api_key is not None:
            return self.api_key

        resp = await self.get(URL.COMMUNITY / "dev/apikey")
        if (
            "<h2>Access Denied</h2>" in resp
            or "You must have a validated email address to create a Steam Web API key" in resp
        ):
            raise RuntimeError("You must have a premium Steam account or validated email address to use this method")

        key_re = re.compile(r"<p>Key: ([0-9A-F]+)</p>")
        if match := key_re.findall(resp):
            self.api_key = match[0]
            return self.api_key

        payload = {
            "domain": "steam.py",
            "agreeToTerms": "agreed",
            "sessionid": self.session_id,
            "Submit": "Register",
        }
        resp = await self.post(URL.COMMUNITY / "dev/registerkey", data=payload)
        self.api_key = key_re.findall(resp)[0]
        return self.api_key

    @utils.cached_property
    def session_id(self) -> str:
        return randbytes(16).hex()

    async def close(self) -> None:
        await self._session.close()

    async def get_user(self, user_id64: ID64) -> user.User | None:
        return await anext(self.get_users((user_id64,)), None)

    async def get_users(self, user_id64s: Iterable[ID64]) -> AsyncGenerator[user.User, None]:
        for data in await asyncio.gather(  # gather all the requests concurrently
            *(
                self.get(
                    api_route("ISteamUser/GetPlayerSummaries", version=2),
                    params={"steamids": ",".join(map(str, sublist))},
                )
                for sublist in utils.as_chunks(user_id64s, 100)
            )
        ):
            data: ResponseDict[dict[Literal["players"], list[user.User]]]
            for user in data["response"]["players"]:
                yield user

    async def get_user_escrow(self, user_id64: ID64, token: str | None) -> user.TradeHoldDurations:
        params = {
            "steamid_target": user_id64,
            "trade_offer_access_token": token if token is not None else "",
        }
        data: ResponseDict[user.TradeHoldDurations] = await self.get(
            api_route("IEconService/GetTradeHoldDurations"), params=params
        )
        return data["response"]

    async def get_friends_ids(self, user_id64: ID64) -> list[ID64]:
        params = {
            "steamid": user_id64,
            "relationship": "friend",
        }
        friends: user.FriendsList = await self.get(api_route("ISteamUser/GetFriendList"), params=params)
        return cast("list[ID64]", [int(friend["steamid"]) for friend in friends["friendslist"]["friends"]])

    async def get_user_clans(self, user_id64: ID64) -> list[ID64]:
        params = {"steamid": user_id64}
        data: user.GetUserGroupList = await self.get(api_route("ISteamUser/GetUserGroupList"), params=params)
        return [parse_id64(group["gid"], type=Type.Clan) for group in data["response"]["groups"]]

    async def get_user_bans(self, *user_id64s: ID64) -> list[user.UserBan]:
        params = {"steamids": ",".join(str(id64) for id64 in user_id64s)}
        data: user.GetPlayerBans = await self.get(api_route("ISteamUser/GetPlayerBans"), params=params)
        return [
            {
                "steamid": ID64(int(ban["SteamId"])),
                "community_banned": ban["CommunityBanned"],
                "vac_banned": ban["VACBanned"],
                "number_of_vac_bans": ban["NumberOfVACBans"],
                "days_since_last_ban": ban["DaysSinceLastBan"],
                "number_of_game_bans": ban["NumberOfGameBans"],
                "economy_ban": ban["EconomyBan"],
            }
            for ban in data["players"]
        ]

    async def get_user_level(self, user_id64: ID64) -> int:
        params = {"steamid": user_id64}
        resp: user.GetSteamLevel = await self.get(api_route("IPlayerService/GetSteamLevel"), params=params)
        return resp["response"]["player_level"]

    async def get_user_badges(self, user_id64: ID64) -> user.UserBadges:
        params = {"steamid": user_id64}
        data: ResponseDict[user.UserBadges] = await self.get(api_route("IPlayerService/GetBadges"), params=params)
        return data["response"]

    async def get_user_community_badge_progress(
        self, user_id64: ID64, badge_id: int
    ) -> list[user.CommunityBadgeProgressQuest]:
        params = {
            "steamid": user_id64,
            "badgeid": badge_id,
        }
        data: ResponseDict[dict[Literal["quests"], list[user.CommunityBadgeProgressQuest]]] = await self.get(
            api_route("IPlayerService/GetCommunityBadgeProgress"), params=params
        )
        return data["response"]["quests"]

    async def get_user_recently_played_apps(self, user_id64: ID64) -> list[app.UserRecentlyPlayedApp]:
        params = {"steamid": user_id64}
        data: ResponseDict[dict[Literal["games"], list[app.UserRecentlyPlayedApp]]] = await self.get(
            api_route("IPlayerService/GetRecentlyPlayedGames"), params=params
        )
        return data["response"]["games"]

    async def get_user_wishlist(self, user_id64: ID64) -> AsyncGenerator[tuple[AppID, app.WishlistApp], None]:
        params = {"p": 0}
        while True:
            resp: dict[AppID, app.WishlistApp] = await self.get(
                URL.STORE / f"wishlist/profiles/{user_id64}/wishlistdata", params=params
            )
            if not resp:  # it's an empty list sometimes lol
                return
            for app_id, data in resp.items():
                yield app_id, data
            params["p"] += 1

    async def get_user_inventory(
        self, user_id64: int, app_id: int, context_id: int, language: Language | None
    ) -> trade.Inventory:
        count = 2000
        ret: trade.Inventory = {"assets": [], "descriptions": [], "last_assetid": 0, "more_items": True}  # type: ignore
        while ret["more_items"]:
            params = {
                "count": count,
                "l": (language or self.language).api_name,
                "start_assetid": ret["last_assetid"],
            }
            resp: trade.Inventory = await self.get(
                URL.COMMUNITY / f"inventory/{user_id64}/{app_id}/{context_id}", params=params
            )
            ret["assets"].extend(resp["assets"])
            ret["descriptions"].extend(resp["descriptions"])
            ret["last_assetid"] = resp.get("last_assetid", 0)
            ret["more_items"] = resp.get("more_items", False)
        return ret

    async def get_user_inventory_info(self, user_id64: ID64) -> ValuesView[user.InventoryInfo]:
        resp = await self.get(URL.COMMUNITY / f"profiles/{user_id64}/inventory")
        soup = BeautifulSoup(resp, "html.parser")
        for script in soup.find_all("script", type="text/javascript"):
            if match := re.search(r"var\s+g_rgAppContextData\s*=\s*(?P<json>{.*?});\s*", script.text):
                break
        else:
            raise ValueError("Could not find inventory info")

        return JSON_LOADS(match["json"]).values()

    async def send_user_gift(
        self, user_id: ID32, asset_id: AssetID, name: str, message: str, closing_note: str, signature: str
    ) -> None:
        payload = {
            "GifteeAccountID": user_id,
            "GifteeEmail": "",
            "GifteeName": name,
            "GiftMessage": message,
            "GiftSentiment": closing_note,
            "GiftSignature": signature,
            "GiftGID": asset_id,
            "SessionID": self.session_id,
        }
        headers = {"Referer": f"{URL.STORE}/checkout/sendgift/{asset_id}"}
        data: EResultSuccess = await self.post(URL.STORE / "checkout/sendgiftsubmit", data=payload, headers=headers)
        if data["success"] != Result.OK:
            raise RuntimeError("Failed to send gift")

    async def get_trade_offers(
        self,
        active_only: bool = True,
        sent: bool = True,
        received: bool = True,
        updated_only: bool = True,
        language: Language | None = None,
    ) -> trade.GetTradeOffers:
        params = {
            "active_only": str(active_only).lower(),
            "get_sent_offers": str(sent).lower(),
            "get_received_offers": str(received).lower(),
            "get_descriptions": "true",
            "cursor": 0,
            "language": (language or self.language).api_name,
        }
        if updated_only:
            try:
                params["time_historical_cutoff"] = self.trades_last_fetched
            except AttributeError:
                pass
        resp: ResponseDict[trade.GetTradeOffers] = await self.get(
            api_route("IEconService/GetTradeOffers"), params=params
        )
        first_page = resp["response"]
        next_cursor = first_page.get("next_cursor", 0)
        current_cursor = 0
        while current_cursor < next_cursor:
            params["cursor"] = next_cursor
            resp = await self.get(api_route("IEconService/GetTradeOffers"), params=params)
            page = resp["response"]
            for key, value in page.items():
                value_in_first_page = first_page[key]
                if isinstance(value_in_first_page, list):
                    assert isinstance(value, list)
                    value_in_first_page += value

            current_cursor = next_cursor
            try:
                next_cursor = page["next_cursor"]
            except KeyError:
                break

        if updated_only:
            self.trades_last_fetched = int(time())

        return first_page

    async def get_trade_history(
        self, limit: int, include_failed: bool, previous_time: int = 0, language: Language | None = None
    ) -> trade.GetTradeOfferHistory:
        params = {
            "max_trades": limit,
            "get_descriptions": "true",
            "include_total": "true",
            "include_failed": str(include_failed).lower(),
            "start_after_time": previous_time,
            "language": (language or self.language).api_name,
        }
        data: ResponseDict[trade.GetTradeOfferHistory] = await self.get(
            api_route("IEconService/GetTradeHistory"), params=params
        )
        return data["response"]

    async def get_trade(self, trade_id: TradeOfferID, language: Language | None = None) -> trade.GetTradeOffer:
        params = {
            "tradeofferid": trade_id,
            "get_descriptions": "true",
            "language": (language or self.language).api_name,
        }
        data: ResponseDict[trade.GetTradeOffer] = await self.get(api_route("IEconService/GetTradeOffer"), params=params)
        return data["response"]

    def accept_user_trade(self, user_id64: ID64, trade_id: TradeOfferID) -> Coro[trade.AcceptTrade]:
        payload = {
            "sessionid": self.session_id,
            "tradeofferid": trade_id,
            "serverid": 1,
            "partner": user_id64,
            "captcha": "",
        }
        headers = {"Referer": str(URL.COMMUNITY / f"tradeoffer/{trade_id}")}
        return self.post(URL.COMMUNITY / f"tradeoffer/{trade_id}/accept", data=payload, headers=headers)

    def _cancel_user_trade(self, trade_id: TradeOfferID, option: str) -> Coro[None]:
        payload = {"sessionid": self.session_id}
        return self.post(URL.COMMUNITY / f"tradeoffer/{trade_id}/{option}", data=payload)

    def decline_user_trade(self, trade_id: TradeOfferID) -> Coro[None]:
        return self._cancel_user_trade(trade_id, "decline")

    def cancel_user_trade(self, trade_id: TradeOfferID) -> Coro[None]:
        return self._cancel_user_trade(trade_id, "cancel")

    def send_trade_offer(
        self,
        user: IndividualID,
        sending: list[trade.AssetToDict],
        receiving: list[trade.AssetToDict],
        token: str | None,
        offer_message: str,
        **kwargs: Any,
    ) -> Coro[trade.TradeOfferCreateResponse]:
        payload = {
            "sessionid": self.session_id,
            "serverid": 1,
            "partner": user.id64,
            "tradeoffermessage": offer_message,
            "json_tradeoffer": JSON_DUMPS(
                {
                    "newversion": True,
                    "version": len(sending) + len(receiving) + 1,
                    "me": {"assets": sending, "currency": [], "ready": False},
                    "them": {"assets": receiving, "currency": [], "ready": False},
                }
            ),
            "captcha": "",
            "trade_offer_create_params": JSON_DUMPS({"trade_offer_access_token": token}) if token is not None else "{}",
            **kwargs,
        }
        referer = URL.COMMUNITY / "tradeoffer/new/" % {"partner": str(user.id)}
        if token is not None:
            referer %= {"token": token}
        headers = {"Referer": str(referer)}
        return self.post(URL.COMMUNITY / "tradeoffer/new/send", data=payload, headers=headers)

    async def get_trade_receipt(self, trade_id: int, language: Language | None = None) -> trade.TradeStatus:
        params = {
            "tradeid": trade_id,
            "get_descriptions": "true",
            "language": (language or self.language).api_name,
        }
        data: ResponseDict[trade.TradeStatus] = await self.get(api_route("IEconService/GetTradeStatus"), params=params)
        return data["response"]

    async def check_availability(self, value: str, type: str) -> bool:
        data = {
            "xml": 1,
            "type": type,
            "value": value,
        }
        xml = await self.post(URL.COMMUNITY / "actions/AvailabilityCheck", data=data)
        soup = BeautifulSoup(xml, "xml")
        return soup.response.bResults.text == "1"  # type: ignore

    async def create_clan(
        self,
        name: str,
        abbreviation: str | None,
        community_url_path: str | None,
        public: bool,
    ) -> ID64:
        if not await self.check_availability(name, "groupName"):
            raise ValueError("Name is not available")
        abbreviation = abbreviation or name
        if not 0 < len(abbreviation) < 12:
            raise ValueError("Abbreviation must be between 1 and 12 characters")
        if not await self.check_availability(abbreviation, "abbreviation"):
            raise ValueError("Abbreviation is not available")
        community_url_path = community_url_path or name
        if not await self.check_availability(community_url_path, "groupLink"):
            raise ValueError("Community URL path is not available")

        data = {
            "sessionID": self.session_id,
            "step": 2,  # might need to be 1 then 2
            "groupName": name,
            "abbreviation": abbreviation or name,
            "groupLink": community_url_path or name,
            "bIsPublic": int(public),
        }
        edit_page = await self.post(URL.COMMUNITY / "actions/GroupCreate", data=data)
        soup = BeautifulSoup(edit_page, "html.parser")
        for element in soup.find_all("div", class_="formRow"):
            row_title = element.find("div", class_="formRowTitle")
            if row_title and "ID" in row_title.text.strip():
                return parse_id64(element.find("div", class_="formRowFields").text.strip(), type=Type.Clan)
        raise RuntimeError("Could not find ID should be unreachable")

    async def edit_clan(
        self,
        clan_id64: ID64,
        *,
        abbreviation: str | None = None,
        headline: str | None = None,
        summary: str | None = None,
        community_url_path: str | None = None,
        language: Language | None = None,
        country: str | None = None,
        state: str | None = None,
        city: str | None = None,
        apps: Iterable[AppID] | None = None,
    ) -> None:
        data = {
            "sessionID": self.session_id,
            "type": "profileSave",
            "abbreviation": abbreviation or "",
            "headline": headline or "",
            "summary": summary or "",
            "customURL": community_url_path or "",
            "language": language.api_name if language is not None else "",
            "country": country or "",
            "state": state or "",
            "city": city or "",
            "favorite_games": ",".join(map(str, apps)) if apps is not None else "",
        }
        return await self.post(f"{ID(clan_id64).community_url}/edit", data=data)

    def join_clan(self, clan_id64: ID64) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "action": "join",
        }
        return self.post(URL.COMMUNITY / f"gid/{clan_id64}", data=payload)

    def leave_clan(self, clan_id64: ID64) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "action": "leaveGroup",
            "groupId": clan_id64,
        }
        return self.post(URL.COMMUNITY / "my/home_process", data=payload)

    def invite_user_to_clan(self, user_id64: ID64, clan_id64: ID64) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "group": clan_id64,
            "invitee": user_id64,
            "type": "groupInvite",
        }
        return self.post(URL.COMMUNITY / "actions/GroupInvite", data=payload)

    def clear_nickname_history(self) -> Coro[None]:
        payload = {"sessionid": self.session_id}
        return self.post(URL.COMMUNITY / "my/ajaxclearaliashistory", data=payload)

    def get_price(self, app_id: AppID, item_name: str, currency: Currency | None) -> Coro[PriceOverviewDict]:
        params = {
            "appid": app_id,
            "market_hash_name": item_name,
        }
        if currency is not None:
            params |= {"currency": currency}

        return self.get(URL.COMMUNITY / "market/priceoverview", params=params)

    async def get_clan_members(self, clan_id64: ID64) -> AsyncGenerator[ID32, None]:
        url = f"{ID(clan_id64).community_url}/members"
        page = 1
        number_of_pages = None

        while number_of_pages is None or page <= number_of_pages:
            resp = await self.get(url, params={"p": page, "content_only": "true"})
            soup = BeautifulSoup(resp, HTML_PARSER)
            if not number_of_pages:
                page_select = soup.find("div", class_="group_paging")
                assert page_select is not None
                number_of_pages = int(re.findall(r"\d* - (\d*)", page_select.text)[0])

            for s in soup.find_all("div", id="memberList"):
                for user in s.find_all("div", class_="member_block"):
                    yield int(user["data-miniprofile"])  # type: ignore
            page += 1

    async def get_clan_invitees(self) -> dict[ID64, ID64]:
        # N.B. can only be invited by one person at a time
        resp = await self.get(URL.COMMUNITY / "my/groups/pending", params={"ajax": "1"})
        soup = BeautifulSoup(resp, HTML_PARSER)
        elements = soup.find_all("a", class_="linkStandard")

        return {
            ID64(
                int(
                    CLAN_ID64_FROM_URL_REGEX.search(clan_element)["steamid"],  # type: ignore
                )
            ): parse_id64(invitee_element["data-miniprofile"])
            for (clan_element, invitee_element) in zip(
                (element for element in elements if "steamLink" in element["class"]),
                (element for element in elements if "data-miniprofile" in element.attrs),
            )
        }

    async def get_clan_announcement_ids(self, clan_id64: ID64) -> list[int]:
        rss = await self.get(URL.COMMUNITY / f"gid/{clan_id64}/rss")
        soup = BeautifulSoup(rss, HTML_PARSER)
        return [
            int(match[0])
            for url in soup.find_all("guid")
            if (match := re.findall(r"announcements/detail/(\d+)", url.text))
        ]

    async def get_clan_events_for(self, clan_id64: ID64, date: date) -> list[int]:
        xml = await self.post(
            URL.COMMUNITY / f"gid/{clan_id64}/events",
            data={"xml": 1, "action": "eventFeed", "month": date.month, "year": date.year},
        )
        soup = BeautifulSoup(xml, HTML_PARSER)
        return [
            int(url.rpartition("/")[2])
            for event_title in soup.find_all("div", class_="eventBlockTitle")
            for url in event_title.a.get("href")
            if url
        ]

    def _edit_clan_event(
        self,
        action: str,
        clan_id64: ID64,
        name: str,
        description: str,
        event_type: str,
        app_id: str,
        server_ip: str,
        server_password: str,
        start: datetime | None,
        event_id: int | None,
    ) -> Coro[str]:
        if start is None:
            tz_offset = int(datetime.now().astimezone().tzinfo.utcoffset(None).total_seconds())  # type: ignore  # PEP 696 should solve this in typeshed
            start_date = "MM/DD/YY"
            start_hour = "12"
            start_minute = "00"
            start_ampm = "PM"
            time_choice = "quick"
        else:
            if start.tzinfo is None:
                start = start.astimezone()
            assert start.tzinfo is not None
            tz_offset = int(start.tzinfo.utcoffset(None).total_seconds())  # type: ignore

            start_date = f"{start:%m/%d/%y}"
            start_hour = f"{start:%I}"
            start_minute = f"{start:%M}"
            start_ampm = "AM" if start.hour <= 12 else "PM"
            time_choice = "specific"

        data = {
            "sessionid": self.session_id,
            "action": action,
            "tzOffset": tz_offset,
            "name": name,
            "type": event_type,
            "appID": app_id,
            "serverIP": server_ip,
            "serverPassword": server_password,
            "notes": description,
            "eventQuickTime": "now",
            "startDate": start_date,
            "startHour": start_hour,
            "startMinute": start_minute,
            "startAMPM": start_ampm,
            "timeChoice": time_choice,
        }

        if event_id is not None:
            data["eventID"] = event_id

        return self.post(URL.COMMUNITY / f"gid/{clan_id64}/eventEdit", data=data)

    def create_clan_event(self, *args: Any, **kwargs: Any) -> Coro[str]:
        return self._edit_clan_event("newEvent", *args, event_id=None, **kwargs)

    def edit_clan_event(self, *args: Any, **kwargs: Any) -> Coro[str]:
        return self._edit_clan_event("updateEvent", *args, **kwargs)

    def delete_clan_event(self, clan_id64: ID64, event_id: int) -> Coro[None]:
        data = {
            "sessionid": self.session_id,
            "action": "deleteEvent",
            "eventID": event_id,
        }
        return self.post(URL.COMMUNITY / f"gid/{clan_id64}/events", data=data)

    async def get_clan_events(self, clan_id: int, event_ids: Sequence[int]) -> list[clan.Event]:
        params = {
            "clanid_list": ",".join([str(clan_id)] * len(event_ids)),
            "uniqueid_list": ",".join(str(id) for id in event_ids),
        }
        data: dict[Literal["events"], list[clan.Event]] = await self.get(
            URL.STORE / "events/ajaxgeteventdetails", params=params
        )
        return data["events"]

    def create_clan_announcement(
        self, clan_id64: ID64, name: str, description: str, hidden: bool = False
    ) -> Coro[None]:
        data = {
            "sessionID": self.session_id,
            "action": "post",
            "headline": name,
            "body": description,
            "languages[0][headline]": name,
            "languages[0][body]": description,
        }
        if hidden:
            data["is_hidden"] = "is_hidden"
        return self.post(URL.COMMUNITY / f"gid/{clan_id64}/announcements", data=data)

    def edit_clan_announcement(self, clan_id64: ID64, announcement_id: int, name: str, description: str) -> Coro[None]:
        data = {
            "sessionID": self.session_id,
            "gid": announcement_id,
            "action": "update",
            "headline": name,
            "body": description,
            "languages[0][headline]": name,
            "languages[0][body]": description,
            "languages[0][updated]": 1,
        }
        return self.post(URL.COMMUNITY / f"gid/{clan_id64}/announcements", data=data)

    def delete_clan_announcement(self, clan_id64: ID64, announcement_id: int) -> Coro[None]:
        params = {
            "sessionID": self.session_id,
        }
        return self.post(URL.COMMUNITY / f"gid/{clan_id64}/announcements/delete/{announcement_id}", params=params)

    async def get_clan_announcement(
        self,
        clan_id: int,
        announcement_id: int,
    ) -> clan.Event:
        params = {
            "clan_accountid": clan_id,
            "announcement_gid": announcement_id,
        }
        data: clan.GetClanAnnouncement = await self.get(URL.STORE / "events/ajaxgetpartnerevent", params=params)
        return data["event"]

    def vote_on_user_post(self, user_id64: ID64, post_id: PostID, vote: int) -> Coro[None]:
        data = {
            "sessionid": self.session_id,
            "vote": vote,
        }

        return self.post(URL.COMMUNITY / f"comment/UserStatusPublished/voteup/{user_id64}/{post_id}", data=data)

    def post_review(
        self,
        app_id: AppID,
        content: str,
        upvoted: bool,
        public: bool,
        commentable: bool,
        received_compensation: bool,
        language: str,
    ) -> Coro[None]:
        data = {
            "appid": app_id,
            "steamworksappid": app_id,
            "comment": content,
            "rated_up": str(upvoted).lower(),
            "is_public": str(public).lower(),
            "language": language,
            "received_compensation": int(received_compensation),
            "disable_comments": int(not commentable),
            "sessionid": self.session_id,
        }

        return self.post(URL.STORE / "friends/recommendgame", data=data)

    def get_reviews(
        self, app_id: AppID, filter: str, review_type: str, purchase_type: str, cursor: str = "*"
    ) -> Coro[dict[str, Any]]:
        params = {
            "json": 1,
            "num_per_page": 100,
            "cursor": urllib.parse.quote(cursor),
            "filter": filter,
            "review_type": review_type,
            "purchase_type": purchase_type,
        }

        return self.get(URL.STORE / f"appreviews/{app_id}", params=params)

    def mark_review_as_helpful(self, review_id: int, rated_up: bool) -> Coro[None]:
        data = {
            "rateup": str(rated_up).lower(),
            "sessionid": self.session_id,
        }
        return self.post(URL.COMMUNITY / f"userreviews/rate/{review_id}", data=data)

    def mark_review_as_funny(self, review_id: int) -> Coro[None]:
        data = {
            "tagid": 1,
            "rateup": "true",
            "sessionid": self.session_id,
        }
        return self.post(URL.COMMUNITY / f"userreviews/votetag/{review_id}", data=data)

    def delete_review(self, app_id: AppID) -> Coro[None]:
        data = {
            "action": "delete",
            "appid": app_id,
            "sessionid": self.session_id,
        }
        return self.post(URL.COMMUNITY / "my/recommended", data=data)

    def get_app(self, app_id: AppID, language: Language | None) -> Coro[dict[str, Any]]:
        params = {
            "appids": app_id,
            "l": (language or self.language).api_name,
        }
        return self.get(URL.STORE / "api/appdetails", params=params)

    def get_app_dlc(self, app_id: AppID, language: Language | None) -> Coro[dict[str, Any]]:
        params = {
            "appid": app_id,
            "l": (language or self.language).api_name,
        }
        return self.get(URL.STORE / "api/dlcforapp", params=params)

    async def get_app_asset_prices(self, app_id: AppID, currency: Currency | None = None) -> app.AssetPrices:
        params = {
            "appid": app_id,
        }
        if currency is not None:
            params |= {
                "currency": currency.name,
            }

        data: dict[Literal["result"], app.AssetPrices] = await self.get(
            api_route("ISteamEconomy/GetAssetPrices"), params=params
        )
        return data["result"]

    def get_app_suggestions(
        self, term: str, language: Language | None = None
    ) -> Coro[list[dict[{"name": str, "id": str, "type": str}]]]:  # noqa: UP037, F821
        params = {
            "term": term,
            "f": "json",
            "cc": "en",
            "l": (language or self.language).api_name,
        }
        return self.get(URL.STORE / "search/suggest", params=params)

    async def get_all_apps(
        self,
        include_games: bool,
        include_dlc: bool,
        include_software: bool,
        include_videos: bool,
        include_hardware: bool,
        chunk_size: int | None,
        limit: int | None,
        last_app_id: AppID | None = None,
        modified_after: datetime | None = None,
    ) -> AsyncGenerator[app.AppListApp, None]:
        have_more_results = True
        last_app_id = None
        while have_more_results:
            params = {
                "include_games": str(include_games).lower(),
                "include_dlc": str(include_dlc).lower(),
                "include_software": str(include_software).lower(),
                "include_videos": str(include_videos).lower(),
                "include_hardware": str(include_hardware).lower(),
                "max_results": min(chunk_size if chunk_size is not None else 10_000, 50_000),
            }
            if last_app_id is not None:
                params["last_appid"] = last_app_id
            if modified_after is not None:
                params["if_modified_since"] = int(modified_after.timestamp())
            data = await self.get(api_route("IStoreService/GetAppList"), params=params)
            resp = data["response"]
            for app in resp["apps"]:
                yield app
                if limit is not None:
                    limit -= 1
                    if limit == 0:
                        return
            last_app_id = AppID(resp.get("last_appid", 0))
            have_more_results = resp.get("have_more_results", False)

    async def get_app_stats(self, app_id: AppID, language: Language | None) -> achievement.AppAppStats:
        params = {
            "appid": app_id,
            "l": (language or self.language).api_name,
        }
        data: dict[Literal["game"], achievement.AppAppStats] = await self.get(
            api_route("ISteamUserStats/GetSchemaForGame", 2), params=params
        )
        return data["game"]

    async def get_app_leaderboards(self, app_id: AppID, language: Language | None) -> list[app.Leaderboard]:
        params = {
            "xml": 1,
            "l": (language or self.language).api_name,
        }
        xml = await self.get(URL.COMMUNITY / f"stats/{app_id}/leaderboards", params=params)
        soup = BeautifulSoup(xml, HTML_PARSER)
        assert soup.response is not None

        return [
            {
                "id": int(leaderboard.lbid.text),
                "name": leaderboard.find("name").text,
                "display_name": str(leaderboard.display_name.text),
                "entry_count": int(leaderboard.entries.text),
                "sort_method": int(leaderboard.sortmethod.text),
                "display_type": int(leaderboard.displaytype.text),
            }
            for leaderboard in soup.response.find_all("leaderboard")
        ]

    async def verify_app_ticket(
        self, app_id: AppID, ticket: str, publisher_key: str | None
    ) -> user.AuthenticateUserTicketParams:
        params = {
            "appid": app_id,
            "ticket": ticket,
        }
        if publisher_key is not None:
            params["key"] = publisher_key
        resp: ResponseDict[user.AuthenticateUserTicket] = await self.get(
            api_route("ISteamUserAuth/AuthenticateUserTicket", publisher=publisher_key is not None),
            params=params,
            api_needs_auth=publisher_key is None,
        )
        return resp["response"]["params"]

    def get_package(self, package_id: PackageID, language: Language | None) -> Coro[dict[str, Any]]:
        params = {
            "packageids": package_id,
            "l": (language or self.language).api_name,
        }
        return self.get(URL.STORE / "api/packagedetails", params=params)

    def redeem_package(self, package_id: PackageID) -> Coro[dict[str, Any]]:
        data = {
            "ajax": "true",
            "sessionid": self.session_id,
        }
        return self.post(URL.STORE / f"freelicense/addfreelicense/{package_id}", data=data)

    def remove_license(self, license_id: PackageID) -> Coro[None]:
        data = {
            "sessionid": self.session_id,
            "packageid": license_id,
        }
        return self.post(URL.STORE / "account/removelicense", data=data)

    def get_bundle(self, bundle_id: BundleID, language: Language | None) -> Coro[list[bundle.Bundle]]:
        params = {
            "bundleids": bundle_id,
            "l": (language or self.language).api_name,
            "cc": "en",
        }
        return self.get(URL.STORE / "actions/ajaxresolvebundles", params=params)

    def redeem_bundle(self, bundle_id: BundleID) -> Coro[dict[str, Any]]:
        data = {
            "ajax": "true",
            "sessionid": self.session_id,
        }
        return self.post(URL.STORE / f"freelicense/addfreebundle/{bundle_id}", data=data)

    def add_wallet_code(self, code: str) -> Coro[AddWalletCode]:
        data = {"wallet_code": code, "sessionid": self.session_id}
        return self.post(URL.STORE / "account/ajaxredeemwalletcode", data=data)

    def add_phone_number(self, phone_number: str) -> Coro[guard.AddPhoneNumber]:
        data = {
            "op": "add_phone_number",
            "arg": phone_number,
            "checkfortos": 0,
            "skipvoip": 0,
            "sessionid": self.session_id,
        }
        return self.post(URL.COMMUNITY / "steamguard/phoneajax", data=data)

    async def edit_profile_info(
        self,
        name: str | None,
        real_name: str | None,
        url: str | None,
        summary: str | None,
        country: str | None,
        state: str | None,
        city: str | None,
    ) -> None:
        info = await self.user.profile_info()

        await self.ensure_logged_in()

        async with self._session.get(URL.COMMUNITY / "my") as r:
            current_url = r.url

        payload = {
            "sessionID": self.session_id,
            "type": "profileSave",
            "weblink_1_title": "",
            "weblink_1_url": "",
            "weblink_2_title": "",
            "weblink_2_url": "",
            "weblink_3_title": "",
            "weblink_3_url": "",
            "personaName": name or self.user.name,
            "real_name": real_name or info.real_name or "",
            "customURL": (url if url is not None else current_url.parts[-2]) or "",
            "country": country or info.country_name,
            "state": state or info.state_name,
            "city": city or info.city_name,
            "summary": summary or info.summary,
            "json": "1",
        }

        await self.post(f"{self.user.community_url}/edit", data=payload)

    async def update_avatar(self, avatar: Media, type: str, *, params: Mapping[str, Any] = {}, **extras: Any) -> None:
        with avatar:
            payload = aiohttp.FormData(fields={k: str(v) for k, v in extras.items()})
            payload.add_field("MAX_FILE_SIZE", str(avatar.size))
            payload.add_field("type", type)
            payload.add_field("sessionid", self.session_id)
            payload.add_field("doSub", "1")
            payload.add_field(
                "avatar", avatar.read(), filename=f"avatar.{avatar.type}", content_type=f"image/{avatar.type}"
            )
            await self.post(URL.COMMUNITY / "actions/FileUploader", data=payload, params=params)

    async def send_media(self, media: Media, **kwargs: int) -> None:
        contents = media.read()
        payload = {
            "sessionid": self.session_id,
            "l": "english",
            "file_size": media.size,
            "file_name": media.name,
            "file_sha": media.hash(contents),
            "file_image_width": media.width,
            "file_image_height": media.height,
            "file_type": f"image/{media.type}",
        }
        resp = await self.post(URL.COMMUNITY / "chat/beginfileupload", data=payload)

        result = resp["result"]
        url = f'{"https" if result["use_https"] else "http"}://{result["url_host"]}{result["url_path"]}'
        headers = {header["name"]: header["value"] for header in result["request_headers"]}
        await self.request("PUT", url, headers=headers, data=contents)

        payload |= {
            "success": 1,
            "ugcid": result["ugcid"],
            "timestamp": result["timestamp"],
            "hmac": resp["hmac"],
            "spoiler": int(media.spoiler),
        } | kwargs
        await self.post(URL.COMMUNITY / "chat/commitfileupload", data=payload)

    async def send_user_media(self, user_id64: ID64, media: Media) -> None:
        with media:
            await self.send_media(media, friend_steamid=user_id64)

    async def send_chat_media(self, chat_group_id: ChatGroupID, chat_id: ChatID, media: Media) -> None:
        with media:
            await self.send_media(media, chat_group_id=chat_group_id, chat_id=chat_id)

    async def upload_chat_icon(self, media: Media) -> bytes:
        with media:
            payload = aiohttp.FormData()
            payload.add_field("sessionid", self.session_id)
            payload.add_field("avatar", media.read(), filename=media.name, content_type=f"image/{media.type}")
            resp = await self.post(URL.COMMUNITY / "chat/avatarfileupload", data=payload)
            return bytes.fromhex(resp["sha"])
