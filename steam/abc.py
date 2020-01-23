import abc


class BaseUser(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Steam user.
    The following implement this ABC:
    - :class:`~steam.User`
    - :class:`~steam.ClientUser`

    Attributes
    -----------
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

    async def send(self, content=None, *, delete_after=None):
        """|coro|
        Send a message to a certain destination.

        Parameters
        ----------
        content: :class:`str`
            The content of the message to send.
        delete_after: :class:`float`
            If provided deletes the message after waiting
            the

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

        channel = await self._get_channel()
        state = self.state
        if content:
            content = str(content)
        else:
            raise

        data = await state.http.send_message(channel.id, content)

        ret = state.create_message(channel=channel, data=data)
        if delete_after is not None:
            await ret.delete(delay=delete_after)
        return ret
