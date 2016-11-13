from . import casetify
import asyncio
import weakref
import logging
import voluptuous as vol
import os.path
import json

from homeassistant.const import (CONF_NAME, CONF_ID, CONF_DEVICES, CONF_HOST, CONF_TYPE)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import discovery

_LOGGER = logging.getLogger(__name__)

DOMAIN = "caseta"

CONF_BUTTONS = "buttons"
CONF_BRIDGES = "bridges"
CONF_INTEGRATION = "integration"
DEFAULT_TYPE = "dimmer"

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_BRIDGES): vol.All(cv.ensure_list, [
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_DEVICES): vol.All(cv.ensure_list, [
                    {
                        vol.Required(CONF_ID): cv.positive_int,
                        vol.Optional(CONF_NAME): cv.string,
                        vol.Optional(CONF_TYPE, default=DEFAULT_TYPE): vol.In(['dimmer', 'switch', 'remote']),
                    }
                ]),
                vol.Optional(CONF_INTEGRATION): cv.string,
            }
        ]),
    }),
}, extra=vol.ALLOW_EXTRA)

def setup(hass, config):
    # read integration report, caseta_HOST.json
    if CONF_BRIDGES in config[DOMAIN]:
        for bridge in config[DOMAIN][CONF_BRIDGES]:
            devices = []
            fname = os.path.join(hass.config.config_dir, "caseta_" + bridge[CONF_HOST] + ".json")
            _LOGGER.debug("loading %s", fname)
            with open(fname, encoding='utf-8') as conf_file:
                integration = json.load(conf_file)
                # print(integration)
                if "LIPIdList" in integration:
                    # lights and switches are in Zones
                    if "Zones" in integration["LIPIdList"]:
                        for zone in integration["LIPIdList"]["Zones"]:
                            # print(zone)
                            devices.append({CONF_ID: zone["ID"],
                                            CONF_NAME: zone["Name"],
                                            CONF_TYPE: "dimmer"})
                    # remotes are in Devices, except ID 1 which is the bridge itself
                    if "Devices" in integration["LIPIdList"]:
                        for device in integration["LIPIdList"]["Devices"]:
                            # print(device)
                            if device["ID"] != 1 and "Buttons" in device:
                                devices.append({CONF_ID: device["ID"],
                                                CONF_NAME: device["Name"],
                                                CONF_TYPE: "remote",
                                                CONF_BUTTONS: [b["Number"] for b in device["Buttons"]]})
            # patch up integration with devices
            if CONF_DEVICES in bridge:
                for device in bridge[CONF_DEVICES]:
                    found = False
                    for existing in devices:
                        if device[CONF_ID] == existing[CONF_ID]:
                            for k in device:
                                existing[k] = device[k]
                            found = True
                            break
                    if not found:
                        devices.append(device)
            _LOGGER.debug("patched %s", devices)

            # sort devices based on device types
            types = { "remote": [], "switch": [], "dimmer": [] }
            for device in devices:
                types[device["type"]].append(device)
            # print(types)

            # run discovery per type
            for t in types:
                component = t
                if component == "dimmer":
                    component = "light"
                if component == "remote":
                    component = "sensor"
                discovery.load_platform(hass,
                                        component,
                                        DOMAIN,
                                        { CONF_HOST: bridge[CONF_HOST],
                                          CONF_DEVICES: types[t] },
                                        config)

    return True

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
            obj = self.wref()
            if obj:
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
                _LOGGER.debug("Reading caseta for host %s", self._host)
                mode, integration, action, value = yield from self._casetify.read()
                if mode == None:
                    _LOGGER.debug("Read no values from casetify")
                    self._hass.loop.create_task(self._readNext())
                    return
                _LOGGER.debug("Read caseta for host %s: %s %d %d %f", self._host, mode, integration, action, value)
                # walk callbacks
                for callback in self._callbacks:
                    _LOGGER.debug("Invoking callback for host %s", self._host)
                    yield from callback.call(mode, integration, action, value)
            except:
                logging.exception('')
            self._hass.loop.create_task(self._readNext())

        @asyncio.coroutine
        def _ping(self):
            yield from asyncio.sleep(60)
            yield from self._casetify.ping()
            self._hass.loop.create_task(self._ping())

        @asyncio.coroutine
        def open(self):
            _LOGGER.debug("Opening caseta for host %s", self._host)
            if self._casetify != None:
                return True
            _LOGGER.info("Opened caseta for host %s", self._host)
            self._casetify = casetify.Casetify()
            yield from self._casetify.open(self._host)
            return True

        @asyncio.coroutine
        def write(self, mode, integration, action, value):
            if self._casetify == None:
                return False
            yield from self._casetify.write(mode, integration, action, value)
            return True

        @asyncio.coroutine
        def query(self, mode, integration, action):
            if self._casetify == None:
                return False
            yield from self._casetify.query(mode, integration, action)
            return True

        def register(self, callback):
            self._callbacks.append(Caseta.__Callback(callback))

        def start(self, hass):
            _LOGGER.debug("Starting caseta for host %s", self._host)
            if self._hass == None:
                self._hass = hass
                hass.loop.create_task(self._readNext())
                hass.loop.create_task(self._ping())

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
