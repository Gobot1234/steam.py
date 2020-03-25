# -*- coding: utf-8 -*-

"""
MIT License

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

Loosely based on
https://github.com/Rapptz/discord.py/blob/master/discord/abc.py
"""

import abc


class BaseUser(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Steam user.
    The following implement this ABC:
    - :class:`~steam.User`
    - :class:`~steam.ClientUser`

    Attributes
    ----------
    name: :class:`str`
        The user's username.
    steam_id: :class:`steam`
        The user's steam id.
    avatar_url: Optional[:class:`str`]
        The avatar url the user has.
    profile_url: :class:`str`
        A link to the user's profile
    """
    __slots__ = ()


class Messageable(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Steam message.
    The following implement this ABC:
        - :class:`~steam.User`
        - :class:`~steam.Message`
    """

    __slots__ = ()

    async def send(self, content: str):
        """|coro|
        Send a message to a certain destination.

        Parameters
        ----------
        content: :class:`str`
            The content of the message to send.

        Raises
        ------
        ~steam.HTTPException
            Sending the message failed.
        ~steam.Forbidden
            You do not have permission to send the message.

        Returns
        -------
        :class:`~steam.Message`
            The message that was sent.
        """
        # ret = state.create_message(channel=channel, data=data)
        # return ret
        pass
