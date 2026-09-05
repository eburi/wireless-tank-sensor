"""OTA trigger beacon.

Advertises the tank sensor's OTA trigger as a standard iBeacon frame — fixed
UUID, major 0x4B4F ("KO"), minor 0x54<target> ("T" + tank number, 0 = all
tanks) — only while start(target)ed, with a safety timeout. ESPHome's built-in esp32_ble_beacon cannot be
switched off at runtime, hence this component. iBeacon was chosen so the sensor
can use the tracker's native parser and Home Assistant's iBeacon integration
shows the trigger while it is on air. Must match packages/tank-sleep.yaml.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import esp32_ble
from esphome.const import CONF_ID, CONF_UUID

DEPENDENCIES = ["esp32_ble"]

CONF_BLE_ID = "ble_id"
CONF_SAFETY_TIMEOUT = "safety_timeout"

ota_beacon_ns = cg.esphome_ns.namespace("ota_beacon")
OtaBeacon = ota_beacon_ns.class_("OtaBeacon", cg.Component)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(OtaBeacon),
        cv.GenerateID(CONF_BLE_ID): cv.use_id(esp32_ble.ESP32BLE),
        cv.Required(CONF_UUID): cv.uuid,
        cv.Optional(CONF_SAFETY_TIMEOUT, default="6min"): cv.positive_time_period_milliseconds,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    parent = await cg.get_variable(config[CONF_BLE_ID])
    # Reserve a GAP event slot so the controller's advertising verdict reaches gap_event_handler().
    esp32_ble.register_gap_event_handler(parent, var)
    await cg.register_component(var, config)
    uuid_bytes = config[CONF_UUID].bytes  # big-endian, as printed — iBeacon wire order
    cg.add(var.set_uuid(cg.ArrayInitializer(*uuid_bytes)))
    cg.add(var.set_safety_timeout(config[CONF_SAFETY_TIMEOUT]))
