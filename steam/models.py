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
"""


class URL:
    API = 'https://api.steampowered.com'
    COMMUNITY = 'https://steamcommunity.com'
    STORE = 'https://store.steampowered.com'


class Comment:
    """Represents a comment on a Steam profile.

    Attributes
    -----------
    id: :class:`int`
        The comment's id.
    content: :class:`str`
        The comment's content.
    author: :class:`~steam.User`
        The author of the comment.
    created_at: :class:`datetime.datetime`
        The time the comment was posted at.
    """

    __slots__ = ('content', 'id', 'created_at', 'author', '_owner_id', '_state')

    def __init__(self, state, comment_id, content, timestamp, author, owner_id):
        self._state = state
        self.content = content
        self.id = comment_id
        self.created_at = timestamp
        self.author = author
        self._owner_id = owner_id

    def __repr__(self):
        attrs = (
            'id', 'author'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Comment {' '.join(resolved)}>"

    async def report(self) -> None:
        """|coro|
        Reports the comment"""
        params = {
            "gidcomment": self.id,
            "hide": 1
        }
        return self._state.request('POST', f'{URL.COMMUNITY}/comment/Profile/hideandreport/{self._owner_id}',
                                   params=params)

    async def delete(self) -> None:
        """|coro|
        Deletes the comment
        """
        params = {
            "gidcomment": self.id,
        }
        return self._state.request('POST', f'{URL.COMMUNITY}/comment/Profile/delete/{self._owner_id}', params=params)