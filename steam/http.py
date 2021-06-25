"""
The MIT License (MIT)

Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import warnings
from base64 import b64encode
from collections.abc import Callable, Coroutine
from functools import partialmethod
from sys import version_info
from time import time
from typing import TYPE_CHECKING, Any, Optional, TypeVar

import aiohttp
import rsa
from typing_extensions import TypeAlias

from . import errors, utils
from .__metadata__ import __version__
from .models import URL, api_route
from .user import BaseUser, ClientUser
from .utils import cached_property

if TYPE_CHECKING:
    from .client import Client
    from .image import Image
    from .user import User, UserDict

T = TypeVar("T")
log = logging.getLogger(__name__)
StrOrURL = aiohttp.client.StrOrURL
RequestType: TypeAlias = "Coroutine[None, None, Optional[T]]"


async def json_or_text(r: aiohttp.ClientResponse) -> Optional[Any]:
    text = await r.text()
    try:
        if "application/json" in r.headers["Content-Type"]:
            return json.loads(text)
    except KeyError:
        pass
    return text


class HTTPClient:
    """The HTTP Client that interacts with the Steam web API."""

    SUCCESS_LOG = "{method} {url} has received {text}"
    REQUEST_LOG = "{method} {url} with {payload} has returned {status}"

    def __init__(self, client: Client, **options: Any):
        self._session: Optional[aiohttp.ClientSession] = None  # filled in login
        self._client = client

        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.api_key: Optional[str] = None
        self.shared_secret: Optional[str] = None
        self._one_time_code = ""
        self._email_code = ""
        self._captcha_id = "-1"
        self._captcha_text = ""
        self._steam_id = ""

        self.user: Optional[ClientUser] = None
        self.logged_in = False
        self.user_agent = (
            f"steam.py/{__version__} client (https://github.com/Gobot1234/steam.py), "
            f"Python/{version_info.major}.{version_info.minor}, aiohttp/{aiohttp.__version__}"
        )

        self.proxy: Optional[str] = options.get("proxy")
        self.proxy_auth: Optional[aiohttp.BasicAuth] = options.get("proxy_auth")
        self.connector: Optional[aiohttp.BaseConnector] = options.get("connector")

    def recreate(self) -> None:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookies={"Steam_Language": "english"},  # make sure the language is set to english
                connector=self.connector,
            )

    async def request(self, method: str, url: StrOrURL, **kwargs: Any) -> Optional[Any]:  # adapted from d.py
        kwargs["headers"] = {"User-Agent": self.user_agent, **kwargs.get("headers", {})}
        # proxy support
        if self.proxy is not None:
            kwargs["proxy"] = self.proxy
        if self.proxy_auth is not None:
            kwargs["proxy_auth"] = self.proxy_auth

        payload = kwargs.get("data")

        for tries in range(5):
            async with self._session.request(method, url, **kwargs) as r:
                log.debug(
                    self.REQUEST_LOG.format(method=method, url=r.url, payload=f"PAYLOAD: {payload}", status=r.status)
                )

                # even errors have text involved in them so this is safe to call
                data = await json_or_text(r)

                # the request was successful so just return the text/json
                if 200 <= r.status < 300:
                    log.debug(f"{method} {r.url} has received {data}")
                    return data

                # we are being rate limited
                elif r.status == 429:
                    # I haven't been able to get any X-Retry-After headers from the API but we should probably still
                    # handle it
                    log.warning("We are being Rate limited")
                    try:
                        await asyncio.sleep(float(r.headers["X-Retry-After"]))
                    except KeyError:  # steam being un-helpful as usual
                        await asyncio.sleep(2 ** tries)
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
                        self.api_key = kwargs["key"] = await self.get_api_key()
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

    get: Callable[..., RequestType] = partialmethod(request, "GET")
    post: Callable[..., RequestType] = partialmethod(request, "POST")

    def connect_to_cm(self, cm: str) -> Coroutine[None, None, aiohttp.ClientWebSocketResponse]:
        headers = {"User-Agent": self.user_agent}
        return self._session.ws_connect(
            f"wss://{cm}/cmsocket/", headers=headers, proxy=self.proxy, proxy_auth=self.proxy_auth
        )

    async def login(self, username: str, password: str, shared_secret: Optional[str]) -> None:
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.recreate()

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

            data = resp.get("transfer_parameters")
            if data is None:
                raise errors.LoginError(
                    "Cannot perform redirects after login. Steam is likely down, please try again later."
                )

            for url in resp["transfer_urls"]:
                await self.post(url=url, data=data)

            self.api_key = await self.get_api_key()
            if self.api_key is None:
                log.info("Failed to get API key")

                async def get_user(self, user_id64: int) -> dict:
                    user_id = int(user_id64) & 0xFFFFFFFF
                    ret = await self.get(URL.COMMUNITY / f"miniprofile/{user_id}/json")
                    ret["steamid"] = user_id64
                    return ret

                async def get_users(self, user_id64s: list[int]) -> list[dict]:
                    return await asyncio.gather(*(self.get_user(user_id64) for user_id64 in user_id64s))

                BaseUser._patch_without_api()
                self.__class__.get_user = get_user
                self.__class__.get_users = get_users
                warnings.warn(
                    "Some methods of User objects are not available as no API key can be generated", UserWarning
                )
                await self.get(URL.COMMUNITY / "home")

            data = await self.get_user(resp["transfer_parameters"]["steamid"])
            state = self._client._connection
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
        self.user = None
        self._client.dispatch("logout")

    async def _get_rsa_params(self, current_repetitions: int = 0) -> tuple[bytes, int]:
        payload = {"username": self.username, "donotcache": int(time() * 1000)}
        try:
            key_response = await self.post(URL.COMMUNITY / "login/getrsakey", data=payload)
        except Exception as exc:
            raise errors.LoginError("Failed to get RSA key") from exc
        try:
            n = int(key_response["publickey_mod"], 16)
            e = int(key_response["publickey_exp"], 16)
            rsa_timestamp = key_response["timestamp"]
        except KeyError:
            if current_repetitions < 5:
                return await self._get_rsa_params(current_repetitions + 1)
            raise errors.LoginError("Could not obtain rsa-key") from None
        else:
            return b64encode(rsa.encrypt(self.password.encode("utf-8"), rsa.PublicKey(n, e))), rsa_timestamp

    async def _send_login_request(self) -> dict:
        password, timestamp = await self._get_rsa_params()
        payload = {
            "username": self.username,
            "password": password.decode(),
            "emailauth": self._email_code,
            "emailsteamid": self._steam_id,
            "twofactorcode": self._one_time_code,
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

    async def get_user(self, user_id64: int) -> Optional[UserDict]:
        params = {"key": self.api_key, "steamids": user_id64}
        resp = await self.get(api_route("ISteamUser/GetPlayerSummaries", version=2) % params)
        return resp["response"]["players"][0] if resp["response"]["players"] else None

    async def get_users(self, user_id64s: list[int]) -> list[UserDict]:
        ret = []

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

    def add_user(self, user_id64: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0,
        }
        return self.post(URL.COMMUNITY / "actions/AddFriendAjax", data=payload)

    def remove_user(self, user_id64: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
        }
        return self.post(URL.COMMUNITY / "actions/RemoveFriendAjax", data=payload)

    def block_user(self, user_id64: int) -> RequestType:
        payload = {"sessionID": self.session_id, "steamid": user_id64, "block": 1}
        return self.post(URL.COMMUNITY / "actions/BlockUserAjax", data=payload)

    def unblock_user(self, user_id64: int) -> RequestType:
        payload = {"sessionID": self.session_id, "steamid": user_id64, "block": 0}
        return self.post(URL.COMMUNITY / "actions/BlockUserAjax", data=payload)

    def accept_user_invite(self, user_id64: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 1,
        }
        return self.post(URL.COMMUNITY / "actions/AddFriendAjax", data=payload)

    def decline_user_invite(self, user_id64: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0,
        }
        return self.post(URL.COMMUNITY / "actions/IgnoreFriendInviteAjax", data=payload)

    def get_user_games(self, user_id64: int) -> RequestType:
        params = {
            "key": self.api_key,
            "steamid": user_id64,
            "include_appinfo": 1,
            "include_played_free_games": 1,
        }
        return self.get(api_route("IPlayerService/GetOwnedGames"), params=params)

    def get_user_inventory(self, user_id64: int, app_id: int, context_id: int) -> RequestType:
        params = {
            "count": 5000,
        }
        return self.get(URL.COMMUNITY / f"inventory/{user_id64}/{app_id}/{context_id}", params=params)

    def get_user_escrow(self, user_id64: int, token: Optional[str]) -> RequestType:
        params = {
            "key": self.api_key,
            "steamid_target": user_id64,
            "trade_offer_access_token": token if token is not None else "",
        }
        return self.get(api_route("IEconService/GetTradeHoldDurations"), params=params)

    async def get_friends(self, user_id64: int) -> list[UserDict]:
        params = {"key": self.api_key, "steamid": user_id64, "relationship": "friend"}
        friends = await self.get(api_route("ISteamUser/GetFriendList"), params=params)
        return await self.get_users([friend["steamid"] for friend in friends["friendslist"]["friends"]])

    def get_trade_offers(self, active_only: bool = True, sent: bool = True, received: bool = True) -> RequestType:
        params = {
            "key": self.api_key,
            "active_only": int(active_only),
            "get_sent_offers": int(sent),
            "get_descriptions": 1,
            "get_received_offers": int(received),
        }
        return self.get(api_route("IEconService/GetTradeOffers"), params=params)

    def get_trade_history(self, limit: int, previous_time: Optional[int]) -> RequestType:
        params = {
            "key": self.api_key,
            "max_trades": limit,
            "get_descriptions": 1,
            "include_total": 1,
            "start_after_time": previous_time or 0,
        }
        return self.get(api_route("IEconService/GetTradeHistory"), params=params)

    def get_trade(self, trade_id: int) -> RequestType:
        params = {"key": self.api_key, "tradeofferid": trade_id, "get_descriptions": 1}
        return self.get(api_route("IEconService/GetTradeOffer"), params=params)

    def accept_user_trade(self, user_id64: int, trade_id: int) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "tradeofferid": trade_id,
            "serverid": 1,
            "partner": user_id64,
            "captcha": "",
        }
        headers = {"Referer": str(URL.COMMUNITY / f"tradeoffer/{trade_id}")}
        return self.post(URL.COMMUNITY / f"tradeoffer/{trade_id}/accept", data=payload, headers=headers)

    def decline_user_trade(self, trade_id: int) -> RequestType:
        payload = {"key": self.api_key, "tradeofferid": trade_id}
        return self.post(api_route("IEconService/DeclineTradeOffer"), data=payload)

    def cancel_user_trade(self, trade_id: int) -> RequestType:
        payload = {"key": self.api_key, "tradeofferid": trade_id}
        return self.post(api_route("IEconService/CancelTradeOffer"), data=payload)

    def send_trade_offer(
        self,
        user: User,
        to_send: list[dict],
        to_receive: list[dict],
        token: Optional[str],
        offer_message: str,
        **kwargs: Any,
    ) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "serverid": 1,
            "partner": user.id64,
            "tradeoffermessage": offer_message,
            "json_tradeoffer": json.dumps(
                {
                    "newversion": True,
                    "version": 4,
                    "me": {"assets": to_send, "currency": [], "ready": False},
                    "them": {"assets": to_receive, "currency": [], "ready": False},
                }
            ),
            "captcha": "",
            "trade_offer_create_params": json.dumps({"trade_offer_access_token": token}) if token is not None else {},
        }
        payload.update(**kwargs)
        headers = {"Referer": str(URL.COMMUNITY / f"tradeoffer/new/?partner={user.id}")}
        return self.post(URL.COMMUNITY / "tradeoffer/new/send", data=payload, headers=headers)

    def get_cm_list(self, cell_id: int) -> RequestType:
        params = {"cellid": cell_id}
        return self.get(api_route("ISteamDirectory/GetCMList"), params=params)

    def get_comments(self, id64: int, comment_path: str, limit: Optional[int] = None) -> RequestType:
        params = {
            "start": 0,
            "totalcount": 9999999999,
            "count": 9999999999 if limit is None else limit,
        }

        return self.get(URL.COMMUNITY / f"comment/{comment_path}/render/{id64}", params=params)

    def post_comment(self, id64: int, comment_type: str, content: str) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "comment": content,
        }
        return self.post(URL.COMMUNITY / f"comment/{comment_type}/post/{id64}", data=payload)

    def delete_comment(self, id64: int, comment_id: int, comment_type: str) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "gidcomment": comment_id,
        }
        return self.post(URL.COMMUNITY / f"comment/{comment_type}/delete/{id64}", data=payload)

    def report_comment(self, id64: int, comment_id: int, comment_type: str) -> RequestType:
        payload = {"gidcomment": comment_id, "hide": 1}
        return self.post(URL.COMMUNITY / f"comment/{comment_type}/hideandreport/{id64}", data=payload)

    def accept_clan_invite(self, clan_id: int) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "steamid": self.user.id64,
            "ajax": "1",
            "action": "group_accept",
            "steamids[]": clan_id,
        }
        return self.post(URL.COMMUNITY / "my/friends/action", data=payload)

    def decline_clan_invite(self, clan_id: int) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "steamid": self.user.id64,
            "ajax": "1",
            "action": "group_ignore",
            "steamids[]": clan_id,
        }
        return self.post(URL.COMMUNITY / "my/friends/action", data=payload)

    def join_clan(self, clan_id: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "action": "join",
        }
        return self.post(URL.COMMUNITY / f"gid/{clan_id}", data=payload)

    def leave_clan(self, clan_id: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "action": "leaveGroup",
            "groupId": clan_id,
        }
        return self.post(URL.COMMUNITY / "my/home_process", data=payload)

    def invite_user_to_clan(self, user_id64: int, clan_id: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "group": clan_id,
            "invitee": user_id64,
            "type": "groupInvite",
        }
        return self.post(URL.COMMUNITY / "actions/GroupInvite", data=payload)

    def get_user_clans(self, user_id64: int) -> RequestType:
        params = {"key": self.api_key, "steamid": user_id64}
        return self.get(api_route("ISteamUser/GetUserGroupList"), params=params)

    def get_user_bans(self, user_id64: int) -> RequestType:
        params = {"key": self.api_key, "steamids": user_id64}
        return self.get(api_route("ISteamUser/GetPlayerBans"), params=params)

    def get_user_level(self, user_id64: int) -> RequestType:
        params = {"key": self.api_key, "steamid": user_id64}
        return self.get(api_route("IPlayerService/GetSteamLevel"), params=params)

    def get_user_badges(self, user_id64: int) -> RequestType:
        params = {"key": self.api_key, "steamid": user_id64}
        return self.get(api_route("IPlayerService/GetBadges"), params=params)

    def clear_nickname_history(self) -> RequestType:
        payload = {"sessionid": self.session_id}
        return self.post(URL.COMMUNITY / "my/ajaxclearaliashistory", data=payload)

    def clear_notifications(self) -> RequestType:
        return self.get(URL.COMMUNITY / "my/inventory")

    def get_price(self, app_id: int, item_name: str, currency: int) -> RequestType:
        payload = {
            "appid": app_id,
            "market_hash_name": item_name,
        }
        payload.update({"currency": currency} if currency is not None else {})
        return self.post(URL.COMMUNITY / "market/priceoverview", data=payload)

    def get_wishlist(self, user_id64: int) -> RequestType:
        return self.get(URL.STORE / f"wishlist/profiles/{user_id64}/wishlistdata")

    def get_game(self, id: int) -> RequestType:
        return self.get(URL.STORE / "api" / "appdetails", params={"appids": id, "cc": "english"})

    async def edit_profile(
        self,
        name: Optional[str],
        real_name: Optional[str],
        url: Optional[str],
        summary: Optional[str],
        country: Optional[str],
        state: Optional[str],
        city: Optional[str],
        avatar: Optional[Image],
    ) -> None:
        if any((name, real_name, url, summary, country, state, city, avatar)):
            info = await self._client._connection.fetch_user_profile_info(self.user.id64)

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

            await self.post(URL.COMMUNITY / "my/edit", data=payload)
        if avatar is not None:
            payload = aiohttp.FormData()
            payload.add_field("MAX_FILE_SIZE", str(len(avatar)))
            payload.add_field("type", "player_avatar_image")
            payload.add_field("sId", str(self.user.id64))
            payload.add_field("sessionid", self.session_id)
            payload.add_field("doSub", "1")
            payload.add_field(
                "avatar", avatar.read(), filename=f"avatar.{avatar.type}", content_type=f"image/{avatar.type}"
            )
            await self.post(URL.COMMUNITY / "actions/FileUploader", data=payload)

    async def send_user_image(self, user_id64: int, image: Image) -> None:
        payload = {
            "sessionid": self.session_id,
            "l": "english",
            "file_size": len(image),
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

    async def send_group_image(self, destination: tuple[int, int], image: Image) -> None:
        chat_id, channel_id = destination
        payload = {
            "sessionid": self.session_id,
            "l": "english",
            "file_size": len(image),
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

    async def get_api_key(self) -> Optional[str]:
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
