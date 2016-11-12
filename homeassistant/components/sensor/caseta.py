"""
Platform for Caseta sensor.

For more details about this platform, please refer to the documentation
https://home-assistant.io/components/sensor.caseta/
"""
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (CONF_NAME, CONF_ID, CONF_DEVICES, CONF_HOST)
import homeassistant.helpers.config_validation as cv

from homeassistant.components import caseta

import voluptuous as vol
import asyncio
import logging

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): vol.All(cv.ensure_list, [
        {
            vol.Required(CONF_ID): cv.positive_int,
            vol.Required(CONF_NAME): cv.string,
        }
    ]),
    vol.Optional(CONF_HOST, default=None): cv.string,
})

_LOGGER = logging.getLogger(__name__)

class CasetaData:
    def __init__(self, caseta, hass):
        self._caseta = caseta
        self._hass = hass
        self._devices = []
        self._added = {}
        self._later = None

    @property
    def devices(self):
        return self._devices

    @property
    def caseta(self):
        return self._caseta

    def setDevices(self, devices):
        self._devices = devices

    @asyncio.coroutine
    def _checkAdded(self):
        yield from asyncio.sleep(5)
        _LOGGER.info("Checking caseta added")
        for integration in self._added:
            _LOGGER.info("Removing caseta added %d %d", integration, self._added[integration])
            for device in self._devices:
                if device.integration == integration:
                    device._update_state(device.state & ~self._added[integration])
                    yield from device.async_update_ha_state()
                    _LOGGER.info("Removed caseta added %d %d", integration, self._added[integration])
                    break
        self._added.clear()

    @asyncio.coroutine
    def readOutput(self, mode, integration, action, value):
        try:
            # find integration in devices
            if mode == caseta.Caseta.DEVICE:
                _LOGGER.info("Got sensor caseta value: %s %d %d %f", mode, integration, action, value)
                for device in self._devices:
                    if device.integration == integration:
                        state = 0
                        # value 2 = on, 3 = fav, 4 = off
                        # value 5 = up, 6 = down
                        if action == 2:
                            state = 0x1
                        elif action == 3:
                            state = 0x2
                        elif action == 4:
                            state = 0x4
                        elif action == 5:
                            state = 0x8
                        elif action == 6:
                            state = 0x10
                        _LOGGER.info("Found device, updating value")
                        if value == caseta.Caseta.Button.DOWN:
                            _LOGGER.info("Found device, updating value, down")
                            device._update_state(device.state | state)
                            if integration in self._added:
                                self._added[integration] |= state
                            else:
                                self._added[integration] = state
                            if self._later != None:
                                self._later.cancel()
                            _LOGGER.info("scheduling call later")
                            self._later = self._hass.loop.create_task(self._checkAdded())
                            yield from device.async_update_ha_state()
                        elif value == caseta.Caseta.Button.UP:
                            _LOGGER.info("Found device, updating value, up")
                            device._update_state(device.state & ~state)
                            if integration in self._added:
                                self._added[integration] &= ~state
                            yield from device.async_update_ha_state()
                        break
        except:
            logging.exception('')

def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Setup the platform."""
    bridge = caseta.Caseta(config[CONF_HOST])
    yield from bridge.open()

    data = CasetaData(bridge, hass)
    devices = [CasetaPicoRemote(pico, data) for pico in config[CONF_DEVICES]]
    data.setDevices(devices)

    yield from async_add_devices(devices)

    bridge.register(data.readOutput)
    bridge.start(hass)

    return True

class CasetaPicoRemote(Entity):
    """Representation of a Caseta Pico remote."""

    def __init__(self, pico, data):
        """Initialize a Caseta Pico."""
        self._data = data
        self._name = pico['name']
        self._integration = int(pico['id'])
        self._state = 0

    @property
    def integration(self):
        return self._integration

    @property
    def name(self):
        """Return the display name of this pico."""
        return self._name

    @property
    def state(self):
        """State of the pico device."""
        return self._state

    def _update_state(self, state):
        """Update state."""
        self._state = state
