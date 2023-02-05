"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
import urllib.parse
import warnings
from base64 import b64encode
from collections.abc import Callable, Iterable
from datetime import datetime
from sys import version_info
from time import time
from typing import TYPE_CHECKING, Any, TypeVar

import aiohttp
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from yarl import URL as _URL

from . import errors, utils
from .__metadata__ import __version__
from ._const import JSON_DUMPS, JSON_LOADS, URL
from .abc import SteamID
from .enums import Language
from .guard import generate_one_time_code
from .models import PriceOverviewDict, api_route
from .user import ClientUser, _BaseUser
from .utils import cached_property

if TYPE_CHECKING:
    from .client import Client
    from .image import Image
    from .types import game, trade
    from .types.http import Coro, ResponseType, StrOrURL
    from .types.package import FetchedPackage
    from .types.user import User


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

    def __init__(self, client: Client, **options: Any):
        self._session: aiohttp.ClientSession = None  # type: ignore  # filled in login
        self.user: ClientUser = None  # type: ignore
        self._client = client

        self.username: str
        self.password: str
        self.api_key: str | None = None
        self.shared_secret: str | None
        self.language: Language = options.get("language", Language.English)

        self._one_time_code = ""
        self._email_code = ""
        self._captcha_id = "-1"
        self._captcha_text = ""
        self._steam_id = ""

        self.logged_in = False
        self.user_agent = (
            f"steam.py/{__version__} client (https://github.com/Gobot1234/steam.py), "
            f"Python/{version_info.major}.{version_info.minor}, aiohttp/{aiohttp.__version__}"
        )

        self.proxy: str | None = options.get("proxy")
        self.proxy_auth: aiohttp.BasicAuth | None = options.get("proxy_auth")
        self.connector: aiohttp.BaseConnector | None = options.get("connector")
        self.personal_inventory_lock = asyncio.Lock()

    def clear(self) -> None:
        self._session = aiohttp.ClientSession(
            cookies={"Steam_Language": self.language.api_name},
            connector=self.connector,
            json_serialize=JSON_DUMPS,
        )

    async def request(self, method: str, url: StrOrURL, **kwargs: Any) -> Any:  # adapted from d.py
        kwargs["headers"] = {"User-Agent": self.user_agent, **kwargs.get("headers", {})}
        payload = kwargs.get("data")

        for tries in range(5):
            async with self._session.request(method, url, **kwargs, proxy=self.proxy, proxy_auth=self.proxy_auth) as r:
                log.debug("%s %s with PAYLOAD: %s has returned %d", method, r.url, payload, r.status)

                # even errors have text involved in them so this is safe to call
                data = await json_or_text(r)

                # the request was successful so just return the text/json
                if 200 <= r.status < 300:
                    log.debug("%s %s has received %s", method, r.url, data)
                    return data

                # we are being rate limited
                elif r.status == 429:
                    # I haven't been able to get any X-Retry-After headers from the API but we should probably still
                    # handle it
                    log.warning("We are being Rate limited")
                    try:
                        await asyncio.sleep(float(r.headers["X-Retry-After"]))
                    except KeyError:  # steam being un-helpful as usual
                        await asyncio.sleep(2**tries)
                    continue

                # we've received a 500 or 502, an unconditional retry
                elif r.status in {500, 502}:
                    await asyncio.sleep(1 + tries * 3)
                    continue

                # been logged out
                elif 300 <= r.status <= 399 and "login" in r.headers.get("location", ""):
                    log.debug("Logged out of session re-logging in")
                    await self.login(self.username, self.password, self.shared_secret)
                    continue

                elif r.status == 401:
                    if not data:
                        raise errors.HTTPException(r, data)
                    # api key either got revoked or it was never valid
                    if "Access is denied. Retrying will not help. Please verify your <pre>key=</pre>" in data:
                        # time to fetch a new key
                        key = await self.get_api_key()
                        assert key is not None
                        self.api_key = kwargs["key"] = key
                        # retry with our new key

                # the usual error cases
                elif r.status == 403:
                    raise errors.Forbidden(r, data)
                elif r.status == 404:
                    raise errors.NotFound(r, data)
                else:
                    raise errors.HTTPException(r, data)

        # we've run out of retries, raise
        raise errors.HTTPException(r, data)

    def get(self, url: StrOrURL, **kwargs: Any) -> Coro[Any]:
        return self.request("GET", url, **kwargs)

    def post(self, url: StrOrURL, **kwargs: Any) -> Coro[Any]:
        return self.request("POST", url, **kwargs)

    def connect_to_cm(self, cm: str) -> Coro[aiohttp.ClientWebSocketResponse]:
        headers = {"User-Agent": self.user_agent}
        return self._session.ws_connect(
            f"wss://{cm}/cmsocket/", headers=headers, proxy=self.proxy, proxy_auth=self.proxy_auth
        )

    async def login(self, username: str, password: str, shared_secret: str | None) -> None:
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.clear()

        try:
            resp = await self._send_login_request()

            if resp.get("captcha_needed") and resp.get("message") != "Please wait and try again later.":
                self._captcha_id = resp["captcha_gid"]
                print(
                    "Please enter the captcha text at "
                    f"https://steamcommunity.com/login/rendercaptcha/?gid={resp['captcha_gid']}"
                )
                captcha_text = await utils.ainput(">>> ")
                self._captcha_text = captcha_text.strip()
                return await self.login(username, password, shared_secret)

            if not resp["success"]:
                raise errors.InvalidCredentials(resp.get("message", "An unexpected error occurred"))

            jar = self._session.cookie_jar
            cookies = jar.filter_cookies(URL.COMMUNITY)
            for url in resp["transfer_urls"]:
                jar.update_cookies(copy.deepcopy(cookies), _URL(url).origin())

            self.api_key = await self.get_api_key()
            if self.api_key is None:
                log.info("Failed to get API key")

                async def get_user(user_id64: int) -> User:  # this is a lie
                    user_id = user_id64 & 0xFFFFFFFF
                    ret = await self.get(URL.COMMUNITY / f"miniprofile/{user_id}/json")
                    ret["steamid"] = user_id64
                    return ret

                async def get_users(user_id64s: Iterable[int]) -> list[User]:
                    return await asyncio.gather(*(self.get_user(user_id64) for user_id64 in user_id64s))  # type: ignore

                _BaseUser._patch_without_api()
                self.get_user = get_user
                self.get_users = get_users
                warnings.warn(
                    "Some methods of User objects are not available as no API key can be generated", UserWarning
                )
                await self.get(URL.COMMUNITY / "home")

            data = await self.get_user(int(resp["transfer_parameters"]["steamid"]))
            state = self._client._connection
            assert data
            self.user = ClientUser(state=state, data=data)
            state._users[self.user.id64] = self.user
            self.logged_in = True
            self._client.dispatch("login")

        except:
            await self._session.close()
            raise

    @cached_property  # should always be called after making at least one request
    def session_id(self) -> str:
        cookies = self._session.cookie_jar.filter_cookies(URL.COMMUNITY)
        return cookies["sessionid"].value

    async def close(self) -> None:
        await self.logout()
        await self._session.close()

    async def logout(self) -> None:
        log.debug("Logging out of session")
        payload = {"sessionid": self.session_id}
        await self.post(URL.COMMUNITY / "login/logout", data=payload)
        self.logged_in = False
        self.user = None  # type: ignore
        self._client.dispatch("logout")

    async def _get_rsa_params(self) -> tuple[bytes, int]:
        payload = {"username": self.username, "donotcache": int(time() * 1000)}
        try:
            key_response = await self.post(URL.COMMUNITY / "login/getrsakey", data=payload)
        except Exception as exc:
            raise errors.LoginError("Could not obtain RSA key") from exc
        try:
            n = int(key_response["publickey_mod"], 16)
            e = int(key_response["publickey_exp"], 16)
            rsa_timestamp = key_response["timestamp"]
        except KeyError:
            raise errors.LoginError("Could not obtain rsa-key") from None
        else:
            return (
                b64encode(
                    rsa.RSAPublicNumbers(e, n).public_key().encrypt(self.password.encode("utf-8"), padding.PKCS1v15())
                ),
                rsa_timestamp,
            )

    async def _send_login_request(self) -> dict[str, Any]:
        password, timestamp = await self._get_rsa_params()
        payload = {
            "username": self.username,
            "password": password.decode(),
            "emailauth": self._email_code,
            "emailsteamid": self._steam_id,
            "twofactorcode": (
                generate_one_time_code(self.shared_secret) if self.shared_secret is not None else self._one_time_code
            ),
            # attempting this straight away makes login a bit faster for everyone with a shared_secret and doesn't
            # hurt performance for others
            "captchagid": self._captcha_id,
            "captcha_text": self._captcha_text,
            "loginfriendlyname": self.user_agent,
            "rsatimestamp": timestamp,
            "remember_login": True,
            "donotcache": int(time() * 1000),
        }
        try:
            resp = await self.post(URL.COMMUNITY / "login/dologin", data=payload)
            if resp.get("requires_twofactor"):
                self._one_time_code = await self._client.code()
            elif resp.get("emailauth_needed"):
                self._steam_id = resp.get("emailsteamid")
                self._email_code = await self._client.code()
            else:
                return resp
            return await self._send_login_request()
        except errors.LoginError:
            raise
        except Exception as exc:
            try:
                msg = exc.args[0]
            except IndexError:
                msg = None
            raise errors.LoginError(msg) from exc

    async def get_user(self, user_id64: int) -> User | None:
        params = {"key": self.api_key, "steamids": user_id64}
        resp = await self.get(api_route("ISteamUser/GetPlayerSummaries", version=2), params=params)
        return resp["response"]["players"][0] if resp["response"]["players"] else None

    async def get_users(self, user_id64s: Iterable[int]) -> list[User]:
        ret: list[User] = []

        for resp in await asyncio.gather(  # gather all the requests concurrently
            *(
                self.get(
                    api_route("ISteamUser/GetPlayerSummaries", version=2),
                    params={"key": self.api_key, "steamids": ",".join(map(str, sublist))},
                )
                for sublist in utils.chunk(user_id64s, 100)
            )
        ):
            ret.extend(resp["response"]["players"])
        return ret

    def add_user(self, user_id64: int) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0,
        }
        return self.post(URL.COMMUNITY / "actions/AddFriendAjax", data=payload)

    def remove_user(self, user_id64: int) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
        }
        return self.post(URL.COMMUNITY / "actions/RemoveFriendAjax", data=payload)

    def block_user(self, user_id64: int) -> Coro[None]:
        payload = {"sessionID": self.session_id, "steamid": user_id64, "block": 1}
        return self.post(URL.COMMUNITY / "actions/BlockUserAjax", data=payload)

    def unblock_user(self, user_id64: int) -> Coro[None]:
        payload = {"sessionID": self.session_id, "steamid": user_id64, "block": 0}
        return self.post(URL.COMMUNITY / "actions/BlockUserAjax", data=payload)

    def accept_user_invite(self, user_id64: int) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 1,
        }
        return self.post(URL.COMMUNITY / "actions/AddFriendAjax", data=payload)

    def decline_user_invite(self, user_id64: int) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0,
        }
        return self.post(URL.COMMUNITY / "actions/IgnoreFriendInviteAjax", data=payload)

    def get_user_games(self, user_id64: int) -> ResponseType[game.GetOwnedGames]:
        params = {
            "key": self.api_key,
            "steamid": user_id64,
            "include_appinfo": 1,
            "include_played_free_games": 1,
        }
        return self.get(api_route("IPlayerService/GetOwnedGames"), params=params)

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

    async def get_client_user_inventory(
        self, app_id: int, context_id: int, language: Language | None
    ) -> trade.Inventory:
        async with self.personal_inventory_lock:  # requires a lock
            return await self.get_user_inventory(self.user.id64, app_id, context_id, language)

    async def get_item_info(
        self, app_id: int, items: Iterable[tuple[int, int]], language: Language | None
    ) -> dict[tuple[int, int], trade.Description]:
        result: dict[tuple[int, int], trade.Description] = {}

        for chunk in utils.chunk(items, 100):
            params = {
                "key": self.api_key,
                "appid": app_id,
                "class_count": len(chunk),
                "language": (language or self.language).web_api_name,
            }

            for i, (class_id, instance_id) in enumerate(chunk):
                params[f"classid{i}"] = class_id
                params[f"instanceid{i}"] = instance_id

            data = await self.get(api_route("ISteamEconomy/GetAssetClassInfo"), params=params)
            result.update({tuple(map(int, key.split("_"))): value for key, value in data["result"].items()})

        return result

    def get_user_escrow(self, user_id64: int, token: str | None) -> ResponseType[dict[str, Any]]:
        params = {
            "key": self.api_key,
            "steamid_target": user_id64,
            "trade_offer_access_token": token if token is not None else "",
        }
        return self.get(api_route("IEconService/GetTradeHoldDurations"), params=params)

    async def get_friends(self, user_id64: int) -> list[User]:
        params = {"key": self.api_key, "steamid": user_id64, "relationship": "friend"}
        friends = await self.get(api_route("ISteamUser/GetFriendList"), params=params)
        return await self.get_users([friend["steamid"] for friend in friends["friendslist"]["friends"]])

    async def get_trade_offers(
        self,
        active_only: bool = True,
        sent: bool = True,
        received: bool = True,
        updated_only: bool = True,
        language: Language | None = None,
    ) -> dict[str, Any]:  # TODO consider making async iter?
        params = {
            "key": self.api_key,
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
        resp = await self.get(api_route("IEconService/GetTradeOffers"), params=params)
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
                    value_in_first_page += value

            current_cursor = next_cursor
            try:
                next_cursor = page["next_cursor"]
            except KeyError:
                break

        if updated_only:
            self.trades_last_fetched = int(time())

        return first_page

    def get_trade_history(
        self, limit: int, previous_time: int = 0, language: Language | None = None
    ) -> ResponseType[trade.GetTradeOfferHistory]:
        params = {
            "key": self.api_key,
            "max_trades": limit,
            "get_descriptions": "true",
            "include_total": "true",
            "start_after_time": previous_time,
            "language": (language or self.language).api_name,
        }
        return self.get(api_route("IEconService/GetTradeHistory"), params=params)

    def get_trade(self, trade_id: int, language: Language | None = None) -> ResponseType[trade.GetTradeOffer]:
        params = {"key": self.api_key, "tradeofferid": trade_id, "get_descriptions": "true"}
        return self.get(api_route("IEconService/GetTradeOffer"), params=params)

    def accept_user_trade(self, user_id64: int, trade_id: int) -> Coro[dict[str, Any]]:
        payload = {
            "sessionid": self.session_id,
            "tradeofferid": trade_id,
            "serverid": 1,
            "partner": user_id64,
            "captcha": "",
        }
        headers = {"Referer": str(URL.COMMUNITY / f"tradeoffer/{trade_id}")}
        return self.post(URL.COMMUNITY / f"tradeoffer/{trade_id}/accept", data=payload, headers=headers)

    def _cancel_user_trade(self, trade_id: int, option: str) -> Coro[None]:
        payload = {"sessionid": self.session_id}
        return self.post(URL.COMMUNITY / f"tradeoffer/{trade_id}/{option}", data=payload)

    def decline_user_trade(self, trade_id: int) -> Coro[None]:
        return self._cancel_user_trade(trade_id, "decline")

    def cancel_user_trade(self, trade_id: int) -> Coro[None]:
        return self._cancel_user_trade(trade_id, "cancel")

    def send_trade_offer(
        self,
        user: SteamID,
        to_send: list[trade.AssetToDict],
        to_receive: list[trade.AssetToDict],
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
                    "version": len(to_send) + len(to_receive) + 1,
                    "me": {"assets": to_send, "currency": [], "ready": False},
                    "them": {"assets": to_receive, "currency": [], "ready": False},
                }
            ),
            "captcha": "",
            "trade_offer_create_params": JSON_DUMPS({"trade_offer_access_token": token}) if token is not None else "{}",
            **kwargs,
        }
        referer = URL.COMMUNITY / f"tradeoffer/new/?partner={user.id}"
        if token is not None:
            referer %= {"token": token}
        headers = {"Referer": str(referer)}
        return self.post(URL.COMMUNITY / "tradeoffer/new/send", data=payload, headers=headers)

    def get_trade_receipt(self, trade_id: int, language: Language | None = None) -> Coro[dict[str, Any]]:
        params = {
            "key": self.api_key,
            "tradeid": trade_id,
            "get_descriptions": "true",
            "language": (language or self.language).api_name,
        }
        return self.get(api_route("IEconService/GetTradeStatus"), params=params)

    def get_cm_list(self, cell_id: int) -> Coro[dict[str, Any]]:
        params = {
            "cellid": cell_id,
            "cmtype": "websockets",
        }
        return self.get(api_route("ISteamDirectory/GetCMListForConnect"), params=params)

    def join_clan(self, clan_id64: int) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "action": "join",
        }
        return self.post(URL.COMMUNITY / f"gid/{clan_id64}", data=payload)

    def leave_clan(self, clan_id64: int) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "action": "leaveGroup",
            "groupId": clan_id64,
        }
        return self.post(URL.COMMUNITY / "my/home_process", data=payload)

    def invite_user_to_clan(self, user_id64: int, clan_id64: int) -> Coro[None]:
        payload = {
            "sessionID": self.session_id,
            "group": clan_id64,
            "invitee": user_id64,
            "type": "groupInvite",
        }
        return self.post(URL.COMMUNITY / "actions/GroupInvite", data=payload)

    def get_user_clans(self, user_id64: int) -> Coro[dict[str, Any]]:
        params = {"key": self.api_key, "steamid": user_id64}
        return self.get(api_route("ISteamUser/GetUserGroupList"), params=params)

    def get_user_bans(self, user_id64: int) -> Coro[dict[str, Any]]:
        params = {"key": self.api_key, "steamids": user_id64}
        return self.get(api_route("ISteamUser/GetPlayerBans"), params=params)

    def get_user_level(self, user_id64: int) -> Coro[dict[str, Any]]:
        params = {"key": self.api_key, "steamid": user_id64}
        return self.get(api_route("IPlayerService/GetSteamLevel"), params=params)

    def get_user_badges(self, user_id64: int) -> Coro[dict[str, Any]]:
        params = {"key": self.api_key, "steamid": user_id64}
        return self.get(api_route("IPlayerService/GetBadges"), params=params)

    def clear_nickname_history(self) -> Coro[None]:
        payload = {"sessionid": self.session_id}
        return self.post(URL.COMMUNITY / "my/ajaxclearaliashistory", data=payload)

    def get_price(self, app_id: int, item_name: str, currency: int) -> Coro[PriceOverviewDict]:
        payload = {
            "appid": app_id,
            "market_hash_name": item_name,
        }
        payload.update({"currency": currency} if currency is not None else {})
        return self.post(URL.COMMUNITY / "market/priceoverview", data=payload)

    def get_wishlist(self, user_id64: int) -> Coro[dict[str, Any]]:
        return self.get(URL.STORE / f"wishlist/profiles/{user_id64}/wishlistdata")

    def get_game(self, game_id: int, language: Language | None) -> Coro[dict[str, Any]]:
        params = {
            "appids": game_id,
            "l": (language or self.language).api_name,
        }
        return self.get(URL.STORE / "api/appdetails", params=params)

    def get_game_dlc(self, game_id: int, language: Language | None) -> Coro[dict[str, Any]]:
        params = {
            "appid": game_id,
            "l": (language or self.language).api_name,
        }
        return self.get(URL.STORE / "api/dlcforapp", params=params)

    def get_clan_rss(self, clan_id64: int) -> Coro[str]:
        return self.get(URL.COMMUNITY / f"gid/{clan_id64}/rss")

    def _edit_clan_event(
        self,
        action: str,
        clan_id64: int,
        name: str,
        description: str,
        event_type: str,
        game_id: str,
        server_ip: str,
        server_password: str,
        start: datetime | None,
        event_id: int | None,
    ) -> Coro[str]:
        if start is None:
            tz_offset = int((datetime.now().astimezone().tzinfo.utcoffset()).total_seconds())
            start_date = "MM/DD/YY"
            start_hour = "12"
            start_minute = "00"
            start_ampm = "PM"
            time_choice = "quick"
        else:
            if start.tzinfo is None:
                start = start.astimezone()

            offset = start.tzinfo.utcoffset(start)
            tz_offset = int(offset.total_seconds())

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
            "appID": game_id,
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

    def delete_clan_event(self, clan_id64: int, event_id: int) -> Coro[None]:
        data = {
            "sessionid": self.session_id,
            "action": "deleteEvent",
            "eventID": event_id,
        }
        return self.post(URL.COMMUNITY / f"gid/{clan_id64}/events", data=data)

    def get_clan_events(self, clan_id: int, event_ids: list[int]) -> Coro[dict[str, Any]]:
        params = {
            "clanid_list": ",".join([str(clan_id)] * len(event_ids)),
            "uniqueid_list": ",".join(str(id) for id in event_ids),
        }
        return self.get(URL.STORE / "events/ajaxgeteventdetails", params=params)

    def create_clan_announcement(self, clan_id64: int, name: str, description: str, hidden: bool = False) -> Coro[None]:
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

    def edit_clan_announcement(self, clan_id64: int, announcement_id: int, name: str, description: str) -> Coro[None]:
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

    def delete_clan_announcement(self, clan_id64: int, announcement_id: int) -> Coro[None]:
        params = {
            "sessionID": self.session_id,
        }
        return self.post(URL.COMMUNITY / f"gid/{clan_id64}/announcements/delete/{announcement_id}", params=params)

    def get_clan_announcement(
        self,
        clan_id: int,
        announcement_id: int,
    ) -> Coro[dict[str, Any]]:
        params = {
            "clan_accountid": clan_id,
            "announcement_gid": announcement_id,
        }
        return self.get(URL.STORE / "events/ajaxgetpartnerevent", params=params)

    def post_review(
        self,
        game_id: int,
        content: str,
        upvoted: bool,
        public: bool,
        commentable: bool,
        received_compensation: bool,
        language: str,
    ) -> Coro[None]:
        data = {
            "appid": game_id,
            "steamworksappid": game_id,
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
        self, game_id: int, filter: str, review_type: str, purchase_type: str, cursor: str = "*"
    ) -> Coro[dict[str, Any]]:
        params = {
            "json": 1,
            "num_per_page": 100,
            "cursor": urllib.parse.quote(cursor),
            "filter": filter,
            "review_type": review_type,
            "purchase_type": purchase_type,
        }

        return self.get(URL.STORE / f"appreviews/{game_id}", params=params)

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

    def delete_review(self, game_id: int) -> Coro[None]:
        data = {
            "action": "delete",
            "appid": game_id,
            "sessionid": self.session_id,
        }
        return self.post(URL.COMMUNITY / "my/recommended", data=data)

    def get_package(self, package_id: int, language: Language | None) -> Coro[dict[str, Any]]:
        params = {
            "packageids": package_id,
            "l": (language or self.language).api_name,
        }
        return self.get(URL.STORE / "api/packagedetails", params=params)

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
            "real_name": real_name or info.real_name,
            "customURL": url or self.user.community_url,
            "country": country or info.country_name,
            "state": state or info.state_name,
            "city": city or info.city_name,
            "summary": summary or info.summary,
        }

        await self.post(f"{self.user.community_url}/edit", data=payload)

    async def update_avatar(self, avatar: Image) -> None:
        with avatar:
            payload = aiohttp.FormData()
            payload.add_field("MAX_FILE_SIZE", str(avatar.size))
            payload.add_field("type", "player_avatar_image")
            payload.add_field("sId", str(self.user.id64))
            payload.add_field("sessionid", self.session_id)
            payload.add_field("doSub", "1")
            payload.add_field(
                "avatar", avatar.read(), filename=f"avatar.{avatar.type}", content_type=f"image/{avatar.type}"
            )
            await self.post(URL.COMMUNITY / "actions/FileUploader", data=payload)

    async def send_user_image(self, user_id64: int, image: Image) -> None:
        with image:
            payload = {
                "sessionid": self.session_id,
                "l": "english",
                "file_size": image.size,
                "file_name": image.name,
                "file_sha": image.hash,
                "file_image_width": image.width,
                "file_image_height": image.height,
                "file_type": f"image/{image.type}",
            }
            resp = await self.post(URL.COMMUNITY / "chat/beginfileupload", data=payload)

            result = resp["result"]
            url = f'{"https" if result["use_https"] else "http"}://{result["url_host"]}{result["url_path"]}'
            headers = {header["name"]: header["value"] for header in result["request_headers"]}
            await self.request("PUT", url=url, headers=headers, data=image.read())

            payload.update(
                {
                    "success": 1,
                    "ugcid": result["ugcid"],
                    "timestamp": resp["timestamp"],
                    "hmac": resp["hmac"],
                    "friend_steamid": user_id64,
                    "spoiler": int(image.spoiler),
                }
            )
            await self.post(URL.COMMUNITY / "chat/commitfileupload", data=payload)

    async def send_chat_image(self, chat_id: int, channel_id: int, image: Image) -> None:
        with image:
            payload = {
                "sessionid": self.session_id,
                "l": "english",
                "file_size": image.size,
                "file_name": image.name,
                "file_sha": image.hash,
                "file_image_width": image.width,
                "file_image_height": image.height,
                "file_type": f"image/{image.type}",
            }
            resp = await self.post(URL.COMMUNITY / "chat/beginfileupload", data=payload)

            result = resp["result"]
            url = f'{"https" if result["use_https"] else "http"}://{result["url_host"]}{result["url_path"]}'
            headers = {header["name"]: header["value"] for header in result["request_headers"]}
            await self.request("PUT", url=url, headers=headers, data=image.read())

            payload.update(
                {
                    "success": 1,
                    "ugcid": result["ugcid"],
                    "timestamp": resp["timestamp"],
                    "hmac": resp["hmac"],
                    "chat_group_id": channel_id,
                    "chat_id": chat_id,
                    "spoiler": int(image.spoiler),
                }
            )
            await self.post(URL.COMMUNITY / "chat/commitfileupload", data=payload)

    async def get_api_key(self) -> str | None:
        resp = await self.get(URL.COMMUNITY / "dev/apikey")
        if (
            "<h2>Access Denied</h2>" in resp
            or "You must have a validated email address to create a Steam Web API key" in resp
        ):
            return

        key_re = re.compile(r"<p>Key: ([0-9A-F]+)</p>")
        match = key_re.findall(resp)
        if match:
            return match[0]

        payload = {
            "domain": "steam.py",
            "agreeToTerms": "agreed",
            "sessionid": self.session_id,
            "Submit": "Register",
        }
        resp = await self.post(URL.COMMUNITY / "dev/registerkey", data=payload)
        return key_re.findall(resp)[0]
