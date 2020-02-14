class State:

    def __init__(self, loop, client, http):
        self.loop = loop
        self.http = http
        self.client = client
