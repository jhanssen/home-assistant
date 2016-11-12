from . import casetify
import asyncio
import weakref
import logging

_LOGGER = logging.getLogger(__name__)

class Caseta:
    class __Callback(object):
        def __init__(self, callback):
            """Create a new callback calling the method @callback"""
            obj = callback.__self__
            attr = callback.__func__.__name__
            self.wref = weakref.ref(obj, self.object_deleted)
            self.callback_attr = attr
            self.token = None

        @asyncio.coroutine
        def call(self, *args, **kwargs):
            _LOGGER.info("Getting weak callback")
            obj = self.wref()
            if obj:
                _LOGGER.info("Got weak callback")
                attr = getattr(obj, self.callback_attr)
                yield from attr(*args, **kwargs)

        def object_deleted(self, wref):
            """Called when callback expires"""
            pass

    class __Caseta:
        _hosts = {}

        def __init__(self, host):
            self._host = host
            self._casetify = None
            self._hass = None
            self._callbacks = []

        def __str__(self):
            return repr(self) + self._host

        @asyncio.coroutine
        def _readNext(self):
            try:
                _LOGGER.info("Reading caseta for host %s", self._host)
                mode, integration, action, value = yield from self._casetify.read()
                _LOGGER.info("Read caseta for host %s: %s %d %d %f", self._host, mode, integration, action, value)
                # walk callbacks
                for callback in self._callbacks:
                    _LOGGER.info("Invoking callback for host %s", self._host)
                    yield from callback.call(mode, integration, action, value)
            except:
                logging.exception('')
            self._hass.loop.create_task(self._readNext())

        @asyncio.coroutine
        def open(self):
            _LOGGER.info("Opening caseta for host %s", self._host)
            if self._casetify != None:
                return True
            _LOGGER.info("Opened caseta for host %s", self._host)
            self._casetify = casetify.Casetify()
            yield from self._casetify.open(self._host)
            return True

        def write(self, mode, integration, action, value):
            if self._casetify == None:
                return False
            self._casetify.write(mode, integration, action, value)
            return True

        def query(self, mode, integration, action):
            if self._casetify == None:
                return False
            self._casetify.query(mode, integration, action)
            return True

        def register(self, callback):
            self._callbacks.append(Caseta.__Callback(callback))

        def start(self, hass):
            _LOGGER.info("Starting caseta for host %s", self._host)
            if self._hass == None:
                self._hass = hass
                hass.loop.create_task(self._readNext())

        @property
        def host(self):
            return self._host

    OUTPUT = casetify.Casetify.OUTPUT
    DEVICE = casetify.Casetify.DEVICE

    Action = casetify.Casetify.Action
    Button = casetify.Casetify.Button

    def __init__(self, host):
        instance = None
        if host in Caseta.__Caseta._hosts:
            instance = Caseta.__Caseta._hosts[host]
        else:
            instance = Caseta.__Caseta(host)
            Caseta.__Caseta._hosts[host] = instance
        super(Caseta, self).__setattr__("instance", instance)

    def __getattr__(self, name):
        return getattr(self.instance, name)

    def __setattr__(self, name, value):
        setattr(self.instance, name, value)
