import asyncio
import re
import logging
from enum import IntEnum

READ_SIZE = 1024
DEFAULT_USER = b"lutron"
DEFAULT_PASSWORD = b"integration"
CASETA_RE = re.compile(b"~([A-Z]+),([0-9.]+),([0-9.]+),([0-9.]+)\r\n")

_LOGGER = logging.getLogger(__name__)

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

    class State(IntEnum):
        Closed = 1,
        Opening = 2,
        Opened = 3

    def __init__(self):
        self._readbuffer = b""
        self._readlock = asyncio.Lock()
        self._writelock = asyncio.Lock()
        self._state = Casetify.State.Closed

    @asyncio.coroutine
    def open(self, host, port=23, username=DEFAULT_USER, password=DEFAULT_PASSWORD):
        with (yield from self._readlock):
            with (yield from self._writelock):
                if self._state != Casetify.State.Closed:
                    return
                self._state = Casetify.State.Opening

                self._host = host
                self._port = port
                self._username = username
                self._password = password

                self.reader, self.writer = yield from asyncio.open_connection(host, port, loop=Casetify.loop)
                yield from self._readuntil(b"login: ")
                self.writer.write(username + b"\r\n")
                yield from self._readuntil(b"password: ")
                self.writer.write(password + b"\r\n")
                yield from self._readuntil(b"GNET> ")

                self._state = Casetify.State.Opened

    @asyncio.coroutine
    def _readuntil(self, value):
        while True:
            if hasattr(value, "search"):
                # assume regular expression
                m = value.search(self._readbuffer)
                if m:
                    self._readbuffer = self._readbuffer[m.end():]
                    return m
            else:
                where = self._readbuffer.find(value)
                if where != -1:
                    self._readbuffer = self._readbuffer[where + len(value):]
                    return True
            try:
                self._readbuffer += yield from self.reader.read(READ_SIZE)
            except ConnectionResetError as exc:
                return False

    @asyncio.coroutine
    def read(self):
        with (yield from self._readlock):
            if self._state != Casetify.State.Opened:
                return None, None, None, None
            match = yield from self._readuntil(CASETA_RE)
            if match != False:
                # 1 = mode, 2 = integration number, 3 = action number, 4 = value
                try:
                    return match.group(1).decode("utf-8"), int(match.group(2)), int(match.group(3)), float(match.group(4))
                except:
                    print("exception in ", match.group(0))
        if match == False:
            # attempt to reconnect
            _LOGGER.info("Reconnecting to caseta bridge %s", self._host)
            self._state = Casetify.State.Closed
            yield from self.open(self._host, self._port, self._username, self._password)
        return None, None, None, None

    @asyncio.coroutine
    def write(self, mode, integration, action, value, *args):
        if hasattr(action, "value"):
            action = action.value
        with (yield from self._writelock):
            if self._state != Casetify.State.Opened:
                return
            data = "#{},{},{},{}".format(mode, integration, action, value)
            for arg in args:
                if arg != None:
                    data += ",{}".format(arg)
            self.writer.write((data + "\r\n").encode())

    @asyncio.coroutine
    def query(self, mode, integration, action):
        if hasattr(action, "value"):
            action = action.value
        with (yield from self._writelock):
            if self._state != Casetify.State.Opened:
                return
            self.writer.write("?{},{},{}\r\n".format(mode, integration, action).encode())

    @asyncio.coroutine
    def ping(self):
        with (yield from self._writelock):
            if self._state != Casetify.State.Opened:
                return
            self.writer.write(b"?SYSTEM,10\r\n")
