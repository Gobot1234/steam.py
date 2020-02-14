from .abc import Messageable


class Message(Messageable):

    async def _get_channel(self):
        pass

    def __init__(self, data):
        self.author = data['author']

    def __repr__(self):
        return '<Message author={0.author!r}>'.format(self)
