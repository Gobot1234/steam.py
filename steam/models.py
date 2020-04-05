import asyncio
import re
from datetime import datetime

from bs4 import BeautifulSoup


class URL:
    API = 'https://api.steampowered.com'
    COMMUNITY = 'https://steamcommunity.com'
    STORE = 'https://store.steampowered.com'


class Game:
    """Represents a Steam game.

    Parameters
    ----------
    title: Optional[:class:`str`]
        The game's title.
    app_id: Optional[:class:`int`]
        The game's app_id.
    is_steam_game: Optional[bool]
        Whether or not the game is an official Steam game.
        Defaults to ``True``

    Attributes
    -----------
    title: Optional[:class:`str`]
        The game's title.
    app_id: Optional[:class:`int`]
        The game's app_id.
    context_id: :class:`int`
        The context id of the game normally 2.
    """

    __slots__ = ('title', 'app_id', 'context_id', '_is_steam_game', '_game')

    def __init__(self, *, title: str = None, app_id: int = None, is_steam_game: bool = True, context_id: int = 2):
        # user defined stuff
        self.title = title
        self.app_id = app_id
        self.context_id = context_id
        self._is_steam_game = is_steam_game

        # api defined stuff
        # TODO add ^

    def __repr__(self):
        attrs = (
            'title', 'app_id', 'context_id'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Game {' '.join(resolved)}>"

    def __eq__(self, other):
        return isinstance(other, Game) and self.app_id == other.app_id

    def __ne__(self, other):
        return not self.__eq__(other)

    def is_steam_game(self):
        """:class:`bool`: Whether or not the game is an official Steam game."""
        return self._is_steam_game


TF2 = Game(title='Team Fortress 2', app_id=440)
DOTA2 = Game(title='DOTA 2', app_id=570)
CSGO = Game(title='Counter Strike Global-Offensive', app_id=730)
STEAM = Game(title='Steam', app_id=753, context_id=6)


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

    async def report(self):
        """Report a comment"""
        await self._state.http.report_comment(self._owner_id, self.id)

    async def delete(self):
        """Delete a comment"""
        await self._state.http.delete_comment(self._owner_id, self.id)


class AsyncIterator:
    __slots__ = ('before', 'after', 'limit', '_current_iteration', '_state')

    def __init__(self, state, limit, before, after):
        self._state = state
        self.limit = limit
        self.before = before or datetime.utcnow()
        self.after = after or datetime.utcfromtimestamp(0)
        self._current_iteration = 0

    async def flatten(self):
        ret = []
        while 1:
            try:
                item = await self.next()
            except StopAsyncIteration:
                return ret
            else:
                ret.append(item)

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.next()

    async def fill(self):
        self._current_iteration += 1
        if self._current_iteration == 2:
            raise StopAsyncIteration


class CommentsIterator(AsyncIterator):
    __slots__ = ('comments', 'owner', '_user_id') + AsyncIterator.__slots__

    def __init__(self, state, user_id, before, after, limit):
        super().__init__(state, limit, before, after)
        self._user_id = user_id
        self.comments = asyncio.Queue()

    async def fill_comments(self):
        await super().fill()
        from .user import make_steam64, User

        data = await self._state.http.fetch_comments(id64=self._user_id, limit=self.limit)
        self.owner = await self._state.fetch_user(self._user_id)
        soup = BeautifulSoup(data['comments_html'], 'html.parser')
        comments = soup.find_all('div', attrs={'class': 'commentthread_comment responsive_body_text'})
        to_fetch = []

        for comment in comments:
            comment = str(comment)
            timestamp = datetime.utcfromtimestamp(int(re.findall(r'data-timestamp="([0-9]*)"', comment)[0]))
            if self.after < timestamp < self.before:
                comment_id = int(re.findall(r'comment_([0-9]*)', comment)[0])
                author_id = int(re.findall(r'data-miniprofile="([0-9]*)"', comment)[0])
                content = re.findall(rf'id="comment_content_{comment_id}">\s*(.*?)\s*</div>',
                                     comment)[0].replace('<br/>', '\n').strip()
                to_fetch.append(make_steam64(author_id))
                self.comments.put_nowait(Comment(state=self._state, comment_id=comment_id, timestamp=timestamp,
                                                 content=content, author=author_id, owner_id=self._user_id))
                if self.limit is not None:
                    if self.comments.qsize <= self.limit:
                        return
        users = await self._state.http.fetch_profiles(to_fetch)
        for user in users:
            author = User(state=self._state, data=user)
            for comment in self.comments._queue:
                if comment.author == author.id:
                    comment.author = author

    async def next(self):
        await super().next()
        if self.comments.empty():
            await self.fill_comments()
        return self.comments.get_nowait()


class TradesIterator(AsyncIterator):
    __slots__ = ('trades', '_active_only', '_sent', '_received') + AsyncIterator.__slots__

    def __init__(self, state, limit, before, after, active_only, sent, received):
        super().__init__(state, limit, before, after)
        self._active_only = active_only
        self._sent = sent
        self._received = received
        self.trades = asyncio.Queue()

    async def fill_trades(self):
        await super().fill()
        from .trade import TradeOffer

        resp = await self._state.http.fetch_trade_offers(self._active_only, self._sent, self._received)
        data = resp['response']
        for trade in data['trade_offers_sent']:
            if self.after.timestamp() < trade['time_created'] < self.before.timestamp():
                self.trades.put_nowait(TradeOffer(state=self._state, data=trade))
            if self.limit is not None:
                if self.trades.qsize <= self.limit:
                    return

    async def next(self):
        if self.trades.empty():
            await self.fill_trades()
        return self.trades.get_nowait()
