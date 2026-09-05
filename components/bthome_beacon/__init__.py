"""BTHome v2 advertisement beacon.

Broadcasts non-connectable BLE advertisements with BTHome v2 service data
(UUID 0xFCD2): packet id, tank level as the BTHome moisture object (%), and
optionally a uint16 count object carrying the sender resistance in tenths of
an ohm. Home Assistant's Bluetooth/BTHome integration discovers it natively.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor, esp32_ble, sensor
from esphome.const import CONF_ID

DEPENDENCIES = ["esp32_ble"]

CONF_BLE_ID = "ble_id"
CONF_LEVEL = "level"
CONF_COUNT = "count"
CONF_VOLUME = "volume"
CONF_ALMOST_EMPTY = "almost_empty"
CONF_DEVICE_NAME = "device_name"

bthome_beacon_ns = cg.esphome_ns.namespace("bthome_beacon")
BTHomeBeacon = bthome_beacon_ns.class_("BTHomeBeacon", cg.Component)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(BTHomeBeacon),
        cv.GenerateID(CONF_BLE_ID): cv.use_id(esp32_ble.ESP32BLE),
        cv.Required(CONF_LEVEL): cv.use_id(sensor.Sensor),
        cv.Optional(CONF_COUNT): cv.use_id(sensor.Sensor),
        cv.Optional(CONF_VOLUME): cv.use_id(sensor.Sensor),
        cv.Optional(CONF_ALMOST_EMPTY): cv.use_id(binary_sensor.BinarySensor),
        cv.Optional(CONF_DEVICE_NAME, default="BTHome"): cv.string_strict,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    level = await cg.get_variable(config[CONF_LEVEL])
    cg.add(var.set_level_sensor(level))
    if CONF_COUNT in config:
        count = await cg.get_variable(config[CONF_COUNT])
        cg.add(var.set_count_sensor(count))
    if CONF_VOLUME in config:
        vol = await cg.get_variable(config[CONF_VOLUME])
        cg.add(var.set_volume_sensor(vol))
    if CONF_ALMOST_EMPTY in config:
        ae = await cg.get_variable(config[CONF_ALMOST_EMPTY])
        cg.add(var.set_almost_empty_sensor(ae))
    # Advertisement space is tight (31 bytes total): keep the name short.
    cg.add(var.set_device_name(config[CONF_DEVICE_NAME][:12]))
