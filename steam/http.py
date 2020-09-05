# -*- coding: utf-8 -*-

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

import asyncio
import html
import json
import logging
import re
from base64 import b64encode
from sys import version_info
from time import time
from typing import TYPE_CHECKING, Any, Coroutine, List, Optional, Tuple

import aiohttp
import rsa
from bs4 import BeautifulSoup

from . import __version__, errors, utils
from .models import URL, api_route, community_route
from .user import ClientUser

if TYPE_CHECKING:
    from .client import Client
    from .image import Image
    from .user import User

log = logging.getLogger(__name__)
StrOrURL = aiohttp.client.StrOrURL
RequestType = Coroutine[None, None, Optional[Any]]


async def json_or_text(r: aiohttp.ClientResponse) -> Optional[Any]:
    try:
        return await r.json()
    except aiohttp.ContentTypeError:  # steam is too inconsistent to do this properly
        return await r.text()


class HTTPClient:
    """The HTTP Client that interacts with the Steam web API."""

    __slots__ = (
        "_session",
        "_client",
        "username",
        "password",
        "api_key",
        "shared_secret",
        "_one_time_code",
        "_email_code",
        "_captcha_id",
        "_captcha_text",
        "_steam_id",
        "session_id",
        "user",
        "logged_in",
        "user_agent",
    )

    SUCCESS_LOG = "{method} {url} has received {text}"
    REQUEST_LOG = "{method} {url} with {payload} has returned {status}"

    def __init__(self, client: "Client"):
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

        self.session_id: Optional[str] = None
        self.user: Optional[ClientUser] = None
        self.logged_in = False
        self.user_agent = (
            f"steam.py/{__version__} client (https://github.com/Gobot1234/steam.py), "
            f"Python/{version_info[0]}.{version_info[1]}, aiohttp/{aiohttp.__version__}"
        )

    def recreate(self) -> None:
        if self._session.closed:
            self._session = aiohttp.ClientSession()

    async def request(self, method: str, url: StrOrURL, **kwargs) -> Optional[Any]:  # adapted from d.py
        kwargs["headers"] = {"User-Agent": self.user_agent, **kwargs.get("headers", {})}

        for tries in range(5):
            async with self._session.request(method, url, **kwargs) as r:
                payload = kwargs.get("data")
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
                    # I haven't been able to get any X-Retry-After headers
                    # from the API but we should probably still handle it
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
                        self._client.api_key = self.api_key = kwargs["key"] = await self.get_api_key()
                        continue
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

    def connect_to_cm(self, cm: str) -> Coroutine[None, None, aiohttp.ClientWebSocketResponse]:
        headers = {"User-Agent": self.user_agent}
        return self._session.ws_connect(f"wss://{cm}/cmsocket/", headers=headers)

    async def login(self, username: str, password: str, shared_secret: Optional[str]) -> None:
        self.username = username
        self.password = password
        self.shared_secret = shared_secret

        self._session = aiohttp.ClientSession()

        resp = await self._send_login_request()

        if resp.get("captcha_needed") and resp.get("message") != "Please wait and try again later.":
            self._captcha_id = resp["captcha_gid"]
            print(
                "Please enter the captcha text at"
                f" https://steamcommunity.com/login/rendercaptcha/?gid={resp['captcha_gid']}"
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
            await self.request("POST", url=url, data=data)

        self.api_key = self._client.api_key = await self.get_api_key()
        cookies = self._session.cookie_jar.filter_cookies(URL.COMMUNITY)
        self.session_id = cookies["sessionid"].value

        resp = await self.get_user(resp["transfer_parameters"]["steamid"])
        data = resp["response"]["players"][0]
        state = self._client._connection
        self.user = ClientUser(state=state, data=data)
        state._users[self.user.id64] = self.user
        self.logged_in = True
        self._client.dispatch("login")

    async def close(self) -> None:
        await self.logout()
        await self._session.close()

    async def logout(self) -> None:
        log.debug("Logging out of session")
        payload = {"sessionid": self.session_id}
        await self.request("POST", community_route("login/logout"), data=payload)
        self.logged_in = False
        self.user = None
        self._client.dispatch("logout")

    async def _get_rsa_params(self, current_repetitions: int = 0) -> Tuple[bytes, int]:
        payload = {"username": self.username, "donotcache": int(time() * 1000)}
        try:
            key_response = await self.request("POST", community_route("login/getrsakey"), data=payload)
        except Exception as exc:
            raise errors.LoginError("Failed to get RSA key") from exc
        try:
            n = int(key_response["publickey_mod"], 16)
            e = int(key_response["publickey_exp"], 16)
            rsa_timestamp = key_response["timestamp"]
        except KeyError:
            if current_repetitions < 5:
                return await self._get_rsa_params(current_repetitions + 1)
            raise ValueError("Could not obtain rsa-key")
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
            resp = await self.request("POST", community_route("login/dologin"), data=payload)
            if resp.get("requires_twofactor"):
                self._one_time_code = await self._client.code()
            elif resp.get("emailauth_needed"):
                self._steam_id = resp.get("emailsteamid")
                self._email_code = await self._client.code()
            else:
                return resp
            return await self._send_login_request()
        except Exception as exc:
            raise errors.LoginError from exc

    def get_user(self, user_id64: int) -> RequestType:
        params = {"key": self.api_key, "steamids": user_id64}
        return self.request("GET", api_route("ISteamUser/GetPlayerSummaries/v2"), params=params)

    async def get_users(self, user_id64s: List[int]) -> List[dict]:
        ret: List[dict] = []
        if user_id64s == [0]:  # FIXME bandaid
            return ret

        for sublist in utils.chunk(user_id64s, 100):
            params = {"key": self.api_key, "steamids": ",".join(map(str, sublist))}
            resp = await self.request("GET", api_route("ISteamUser/GetPlayerSummaries/v2"), params=params)
            ret.extend(resp["response"]["players"])
        return ret

    def add_user(self, user_id64: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0,
        }
        return self.request("POST", community_route("actions/AddFriendAjax"), data=payload)

    def remove_user(self, user_id64: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
        }
        return self.request("POST", community_route("actions/RemoveFriendAjax"), data=payload)

    def block_user(self, user_id64: int) -> RequestType:
        payload = {"sessionID": self.session_id, "steamid": user_id64, "block": 1}
        return self.request("POST", community_route("actions/BlockUserAjax"), data=payload)

    def unblock_user(self, user_id64: int) -> RequestType:
        payload = {"sessionID": self.session_id, "steamid": user_id64, "block": 0}
        return self.request("POST", community_route("actions/BlockUserAjax"), data=payload)

    def accept_user_invite(self, user_id64: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 1,
        }
        return self.request("POST", community_route("actions/AddFriendAjax"), data=payload)

    def decline_user_invite(self, user_id64: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0,
        }
        return self.request("POST", community_route("actions/IgnoreFriendInviteAjax"), data=payload)

    def get_user_games(self, user_id64: int) -> RequestType:
        params = {
            "key": self.api_key,
            "steamid": user_id64,
            "include_appinfo": 1,
            "include_played_free_games": 1,
        }
        return self.request("GET", api_route("IPlayerService/GetOwnedGames"), params=params)

    def get_user_inventory(self, user_id64: int, app_id: int, context_id: int) -> RequestType:
        params = {
            "count": 5000,
        }
        return self.request("GET", community_route(f"inventory/{user_id64}/{app_id}/{context_id}"), params=params)

    def get_user_escrow(self, user_id64: int, token: Optional[str]) -> RequestType:
        params = {
            "key": self.api_key,
            "steamid_target": user_id64,
            "trade_offer_access_token": token if token is not None else "",
        }
        return self.request("GET", api_route("IEconService/GetTradeHoldDurations"), params=params)

    async def get_friends(self, user_id64: int) -> List[dict]:
        params = {"key": self.api_key, "steamid": user_id64, "relationship": "friend"}
        friends = await self.request("GET", api_route("ISteamUser/GetFriendList"), params=params)
        return await self.get_users([friend["steamid"] for friend in friends["friendslist"]["friends"]])

    def get_trade_offers(self, active_only: bool = True, sent: bool = True, received: bool = True) -> RequestType:
        params = {
            "key": self.api_key,
            "active_only": int(active_only),
            "get_sent_offers": int(sent),
            "get_descriptions": 1,
            "get_received_offers": int(received),
        }
        return self.request("GET", api_route("IEconService/GetTradeOffers"), params=params)

    def get_trade_history(self, limit: int, previous_time: Optional[int]) -> RequestType:
        params = {
            "key": self.api_key,
            "max_trades": limit,
            "get_descriptions": 1,
            "include_total": 1,
            "start_after_time": previous_time or 0,
        }
        return self.request("GET", api_route("IEconService/GetTradeHistory"), params=params)

    def get_trade(self, trade_id: int) -> RequestType:
        params = {"key": self.api_key, "tradeofferid": trade_id, "get_descriptions": 1}
        return self.request("GET", api_route("IEconService/GetTradeOffer"), params=params)

    def accept_user_trade(self, user_id64: int, trade_id: int) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "tradeofferid": trade_id,
            "serverid": 1,
            "partner": user_id64,
            "captcha": "",
        }
        headers = {"Referer": community_route(f"/tradeoffer/{trade_id}")}
        return self.request("POST", community_route(f"tradeoffer/{trade_id}/accept"), data=payload, headers=headers)

    def decline_user_trade(self, trade_id: int) -> RequestType:
        payload = {"key": self.api_key, "tradeofferid": trade_id}
        return self.request("POST", api_route("IEconService/DeclineTradeOffer"), data=payload)

    def cancel_user_trade(self, trade_id: int) -> RequestType:
        payload = {"key": self.api_key, "tradeofferid": trade_id}
        return self.request("POST", api_route("IEconService/CancelTradeOffer"), data=payload)

    def send_trade_offer(
        self,
        user: "User",
        to_send: List[dict],
        to_receive: List[dict],
        token: Optional[str],
        offer_message: str,
        **kwargs,
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
        headers = {"Referer": str(community_route(f"tradeoffer/new/?partner={user.id}"))}
        return self.request("POST", community_route("tradeoffer/new/send"), data=payload, headers=headers)

    def send_counter_trade_offer(
        self,
        trade_id: int,
        user: "User",
        to_send: List[dict],
        to_receive: List[dict],
        token: Optional[str],
        offer_message: str,
    ) -> RequestType:
        return self.send_trade_offer(user, to_send, to_receive, token, offer_message, trade_id=trade_id)

    def get_cm_list(self, cell_id: int) -> RequestType:
        params = {"cellid": cell_id}
        return self.request("GET", api_route("ISteamDirectory/GetCMList"), params=params)

    def get_comments(self, id64: int, comment_type: str, limit: Optional[int] = None) -> RequestType:
        params = {"start": 0, "totalcount": 9999999999}
        if limit is None:
            params["count"] = 9999999999
        else:
            params["count"] = limit
        return self.request("GET", community_route(f"comment/{comment_type}/render/{id64}"), params=params)

    def post_comment(self, id64: int, comment_type: str, content: str) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "comment": content,
        }
        return self.request("POST", community_route(f"comment/{comment_type}/post/{id64}"), data=payload)

    def delete_comment(self, id64: int, comment_id: int, comment_type: str) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "gidcomment": comment_id,
        }
        return self.request("POST", community_route(f"comment/{comment_type}/delete/{id64}"), data=payload)

    def report_comment(self, id64: int, comment_id: int, comment_type: str) -> RequestType:
        payload = {"gidcomment": comment_id, "hide": 1}
        return self.request("POST", community_route(f"comment/{comment_type}/hideandreport/{id64}"), data=payload)

    def accept_clan_invite(self, clan_id: int) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "steamid": self.user.id64,
            "ajax": "1",
            "action": "group_accept",
            "steamids[]": clan_id,
        }
        return self.request("POST", community_route("my/friends/action"), data=payload)

    def decline_clan_invite(self, clan_id: int) -> RequestType:
        payload = {
            "sessionid": self.session_id,
            "steamid": self.user.id64,
            "ajax": "1",
            "action": "group_ignore",
            "steamids[]": clan_id,
        }
        return self.request("POST", community_route("my/friends/action"), data=payload)

    def join_clan(self, clan_id: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "action": "join",
        }
        return self.request("POST", community_route(f"gid/{clan_id}"), data=payload)

    def leave_clan(self, clan_id: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "action": "leaveGroup",
            "groupId": clan_id,
        }
        return self.request("POST", community_route("my/home_process"), data=payload)

    def invite_user_to_clan(self, user_id64: int, clan_id: int) -> RequestType:
        payload = {
            "sessionID": self.session_id,
            "group": clan_id,
            "invitee": user_id64,
            "type": "groupInvite",
        }
        return self.request("POST", community_route("actions/GroupInvite"), data=payload)

    def get_user_clans(self, user_id64: int) -> RequestType:
        params = {"key": self.api_key, "steamid": user_id64}
        return self.request("GET", api_route("ISteamUser/GetUserGroupList"), params=params)

    def get_user_bans(self, user_id64: int) -> RequestType:
        params = {"key": self.api_key, "steamids": user_id64}
        return self.request("GET", api_route("ISteamUser/GetPlayerBans"), params=params)

    def get_user_level(self, user_id64: int) -> RequestType:
        params = {"key": self.api_key, "steamid": user_id64}
        return self.request("GET", api_route("IPlayerService/GetSteamLevel"), params=params)

    def get_user_badges(self, user_id64: int) -> RequestType:
        params = {"key": self.api_key, "steamid": user_id64}
        return self.request("GET", api_route("IPlayerService/GetBadges"), params=params)

    def clear_nickname_history(self) -> RequestType:
        payload = {"sessionid": self.session_id}
        return self.request("POST", community_route("my/ajaxclearaliashistory"), data=payload)

    def clear_notifications(self) -> RequestType:
        return self.request("GET", community_route("my/inventory"))

    def get_price(self, app_id: int, item_name: str, currency: int) -> RequestType:
        payload = {
            "appid": app_id,
            "market_hash_name": item_name,
        }
        payload.update({"currency": currency} if currency is not None else {})
        return self.request("POST", community_route("market/priceoverview"), data=payload)

    async def edit_profile(
        self,
        name: Optional[str],
        real_name: Optional[str],
        url: Optional[str],
        summary: Optional[str],
        country: Optional[str],
        state: Optional[str],
        city: Optional[str],
        avatar: Optional["Image"],
    ) -> None:
        if any((name, real_name, url, summary, country, state, city, avatar)):
            resp = await self.request("GET", url=community_route("my/edit"))
            soup = BeautifulSoup(resp, "html.parser")
            edit_config = str(soup.find("div", attrs={"id": "profile_edit_config"}))
            value = re.findall(
                r'data-profile-edit=[\'"]{(.*?)},',
                html.unescape(edit_config),
                flags=re.S,
            )[0]
            loadable = value.replace("\r", "\\r").replace("\n", "\\n")
            profile = json.loads(f'{"{"}{loadable}{"}}"}')
            for key, value in profile.items():
                if isinstance(value, dict):
                    continue
                profile[key] = str(value).replace("\\r", "\r").replace("\\n", "\n")

            payload = {
                "sessionID": self.session_id,
                "type": "profileSave",
                "weblink_1_title": "",
                "weblink_1_url": "",
                "weblink_2_title": "",
                "weblink_2_url": "",
                "weblink_3_title": "",
                "weblink_3_url": "",
                "personaName": name or profile["strPersonaName"],
                "real_name": real_name or profile["strRealName"],
                "customURL": url or profile["strCustomURL"],
                "country": country or profile["LocationData"]["locCountryCode"],
                "state": state or profile["LocationData"]["locStateCode"],
                "city": city or profile["LocationData"]["locCityCode"],
                "summary": summary or profile["strSummary"],
            }

            await self.request("POST", url=f"{self.user.community_url}/edit", data=payload)
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
            await self.request("POST", community_route("actions/FileUploader"), data=payload)

    async def send_user_image(self, user_id64: int, image: "Image") -> None:
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
        resp = await self.request("POST", community_route("chat/beginfileupload"), data=payload)

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
        await self.request("POST", community_route("chat/commitfileupload"), data=payload)

    async def send_group_image(self, destination: Tuple[int, int], image: "Image") -> None:
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
        resp = await self.request("POST", community_route("chat/beginfileupload"), data=payload)

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
        await self.request("POST", community_route("chat/commitfileupload"), data=payload)

    async def get_api_key(self) -> str:
        resp = await self.request("GET", community_route("dev/apikey"))
        if "<h2>Access Denied</h2>" in resp:
            raise errors.LoginError(
                "Access denied, you will need to generate a key yourself: https://steamcommunity.com/dev/apikey"
            )
        error = "You must have a validated email address to create a Steam Web API key"
        if error in resp:
            raise errors.LoginError(error)

        match = re.findall(r"<p>Key: ([0-9A-F]+)</p>", resp)
        if match:
            return match[0]

        self.session_id = re.findall(r'g_sessionID = "(.*?)";', resp)[0]
        payload = {
            "domain": "steam.py",
            "agreeToTerms": "agreed",
            "sessionid": self.session_id,
            "Submit": "Register",
        }
        resp = await self.request("POST", community_route("dev/registerkey"), data=payload)
        return re.findall(r"<p>Key: ([0-9A-F]+)</p>", resp)[0]
