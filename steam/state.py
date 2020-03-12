class State:
    __slots__ = ('loop', 'http', 'client', 'dispatch', 'request')

    def __init__(self, loop, client, http):
        self.loop = loop
        self.http = http
        self.request = http.request
        self.client = client
        self.dispatch = client.dispatch
