from .abc import Messageable


class Message(Messageable):

    async def _get_channel(self):
        pass

    def __init__(self):
        pass

    def __repr__(self):
        return '<author={0.author} flags={0.flags}>'.format(self)

    @property
    def author(self):
        pass

    @property
    def content(self):
        pass

    @property
    def time_created_at(self):
        pass
