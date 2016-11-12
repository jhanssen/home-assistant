import asyncio
import re
from enum import IntEnum

READ_SIZE = 1024
DEFAULT_USER = b"lutron"
DEFAULT_PASSWORD = b"integration"
CASETA_RE = re.compile(b"~([A-Z]+),([^,\r\n]+),([^,\r\n]+),([^\r\n]+)\r\n")

class Casetify:
    """Async class to communicate with Lutron Caseta"""
    loop = asyncio.get_event_loop()

    OUTPUT = "OUTPUT"
    DEVICE = "DEVICE"

    class Action(IntEnum):
        SET = 1

    class Button(IntEnum):
        DOWN = 3
        UP = 4

    def __init__(self):
        self.readbuffer = b""

    @asyncio.coroutine
    def open(self, host, port=23, username=DEFAULT_USER, password=DEFAULT_PASSWORD):
        self.reader, self.writer = yield from asyncio.open_connection(host, port, loop=Casetify.loop)
        yield from self._readuntil(b"login: ")
        self.writer.write(username + b"\r\n")
        yield from self._readuntil(b"password: ")
        self.writer.write(password + b"\r\n")
        yield from self._readuntil(b"GNET> ")

    @asyncio.coroutine
    def _readuntil(self, value):
        while True:
            if hasattr(value, "search"):
                # assume regular expression
                m = value.search(self.readbuffer)
                if m:
                    self.readbuffer = self.readbuffer[m.end():]
                    return m
            else:
                where = self.readbuffer.find(value)
                if where != -1:
                    self.readbuffer = self.readbuffer[where + len(value):]
                    return True
            self.readbuffer += yield from self.reader.read(READ_SIZE)

    @asyncio.coroutine
    def read(self):
        match = yield from self._readuntil(CASETA_RE)
        # 1 = mode, 2 = integration number, 3 = action number, 4 = value
        return match.group(1).decode("utf-8"), int(match.group(2)), int(match.group(3)), float(match.group(4))

    def write(self, mode, integration, action, value):
        if hasattr(action, "value"):
            action = action.value
        self.writer.write("#{},{},{},{}\r\n".format(mode, integration, action, value).encode())

    def query(self, mode, integration, action):
        if hasattr(action, "value"):
            action = action.value
        self.writer.write("?{},{},{}\r\n".format(mode, integration, action).encode())
