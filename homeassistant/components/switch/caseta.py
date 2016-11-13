"""
Platform for Caseta switches.

For more details about this platform, please refer to the documentation
https://home-assistant.io/components/switch.caseta/
"""
from homeassistant.components.switch import (SwitchDevice, PLATFORM_SCHEMA)
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
    vol.Required(CONF_HOST): cv.string,
})

_LOGGER = logging.getLogger(__name__)

class CasetaData:
    def __init__(self, caseta):
        self._caseta = caseta
        self._devices = []

    @property
    def devices(self):
        return self._devices

    @property
    def caseta(self):
        return self._caseta

    def setDevices(self, devices):
        self._devices = devices

    @asyncio.coroutine
    def readOutput(self, mode, integration, action, value):
        try:
            # find integration in devices
            if mode == caseta.Caseta.OUTPUT:
                _LOGGER.debug("Got switch caseta value: %s %d %d %f", mode, integration, action, value)
                for device in self._devices:
                    if device.integration == integration:
                        if action == caseta.Caseta.Action.SET:
                            _LOGGER.info("Found switch device, updating value")
                            device._update_state(value)
                            yield from device.async_update_ha_state()
                            break
        except:
            logging.exception('')

def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Setup the platform."""
    if discovery_info == None:
        return
    bridge = caseta.Caseta(discovery_info[CONF_HOST])
    yield from bridge.open()

    data = CasetaData(bridge)
    devices = [CasetaSwitch(switch, data) for switch in discovery_info[CONF_DEVICES]]
    data.setDevices(devices)

    for device in devices:
        yield from device.query()

    yield from async_add_devices(devices)

    bridge.register(data.readOutput)
    bridge.start(hass)

    return True

class CasetaSwitch(SwitchDevice):
    """Representation of a Caseta Switch."""

    def __init__(self, switch, data):
        """Initialize a Caseta Switch."""
        self._data = data
        self._name = switch['name']
        self._integration = int(switch['id'])
        self._is_on = False

    @asyncio.coroutine
    def query(self):
        self._data.caseta.query(caseta.Caseta.OUTPUT, self._integration, caseta.Caseta.Action.SET)

    @property
    def integration(self):
        return self._integration

    @property
    def name(self):
        """Return the display name of this switch."""
        return self._name

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._is_on

    @asyncio.coroutine
    def async_turn_on(self, **kwargs):
        """Instruct the switch to turn on."""
        _LOGGER.debug("Writing caseta value: %d %d on", self._integration, caseta.Caseta.Action.SET)
        yield from self._data.caseta.write(caseta.Caseta.OUTPUT, self._integration, caseta.Caseta.Action.SET, 100)

    @asyncio.coroutine
    def async_turn_off(self, **kwargs):
        """Instruct the swtich to turn off."""
        _LOGGER.debug("Writing caseta value: %d %d off", self._integration, caseta.Caseta.Action.SET)
        yield from self._data.caseta.write(caseta.Caseta.OUTPUT, self._integration, caseta.Caseta.Action.SET, 0)

    def _update_state(self, value):
        """Update state."""
        self._is_on = value > 0
