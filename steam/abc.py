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
    id64: :class:`int`
        The user's 64 id.
    avatar_url: Optional[:class:`str`]
        The avatar url the user has.
    profile_url: :class:`str`
        A link to the user's profile
    """
    __slots__ = ()


class Messageable(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Steam user.
        The following implement this ABC:
        - :class:`~steam.User`
        """

    __slots__ = ()

    async def send(self, content: str = None, *, delete_after=None):
        """|coro|
        Send a message to a certain destination.

        Parameters
        ----------
        content: :class:`str`
            The content of the message to send.
        delete_after: :class:`float`
            If provided deletes the message after waiting
            for the timer.

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
        # state = None

        # data = await state.http.send_message(channel=channel, content)

        # ret = state.create_message(channel=channel, data=data)
        # if delete_after is not None:
        # await ret.delete(delay=delete_after)
        # return ret
        pass
