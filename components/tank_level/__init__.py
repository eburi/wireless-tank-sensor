"""Self-calibrating tank level from a resistive sender.

Consumes a raw resistance sensor, learns the sender's usable min/max resistance
conservatively (per the concept doc: filtered input, repeated observations
required, never auto-shrinks), persists calibration to NVS flash, and publishes
a 0-100 % level. EMA state lives in RTC memory so smoothing survives deep sleep.
Kali's sender: low resistance = empty -> invert defaults to false.

Tank content model (M4): float senders have a dead zone below the float's
travel — `reserve_volume` is how many liters the pump can still deliver after
the measured level reads 0 % (found by the on-site pump test), `total_volume`
the tank capacity. With both set, the published level is rescaled to true
content (bottoms out at the reserve fraction instead of lying with 0 %), a
`volume` sensor reports liters, and `almost_empty` (problem class) trips when
the float sits on its bottom stop and the reserve is being drained blind.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor, sensor
from esphome.const import (
    CONF_ID,
    DEVICE_CLASS_PROBLEM,
    STATE_CLASS_MEASUREMENT,
    UNIT_OHM,
    UNIT_PERCENT,
)

AUTO_LOAD = ["binary_sensor"]

CONF_SOURCE = "source"
CONF_LEVEL = "level"
CONF_VOLUME = "volume"
CONF_ALMOST_EMPTY = "almost_empty"
CONF_LEARNED_MIN = "learned_min"
CONF_LEARNED_MAX = "learned_max"
CONF_SEED_MIN = "seed_min"
CONF_SEED_MAX = "seed_max"
CONF_INVERT = "invert"
CONF_TOTAL_VOLUME = "total_volume"
CONF_RESERVE_VOLUME = "reserve_volume"

tank_level_ns = cg.esphome_ns.namespace("tank_level")
TankLevel = tank_level_ns.class_("TankLevel", cg.Component)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(TankLevel),
        cv.Required(CONF_SOURCE): cv.use_id(sensor.Sensor),
        cv.Required(CONF_LEVEL): sensor.sensor_schema(
            unit_of_measurement=UNIT_PERCENT,
            accuracy_decimals=0,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        cv.Optional(CONF_VOLUME): sensor.sensor_schema(
            unit_of_measurement="L",
            accuracy_decimals=1,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        cv.Optional(CONF_ALMOST_EMPTY): binary_sensor.binary_sensor_schema(
            device_class=DEVICE_CLASS_PROBLEM,
        ),
        cv.Optional(CONF_LEARNED_MIN): sensor.sensor_schema(
            unit_of_measurement=UNIT_OHM, accuracy_decimals=1
        ),
        cv.Optional(CONF_LEARNED_MAX): sensor.sensor_schema(
            unit_of_measurement=UNIT_OHM, accuracy_decimals=1
        ),
        cv.Optional(CONF_SEED_MIN, default=3.0): cv.float_,
        cv.Optional(CONF_SEED_MAX, default=183.0): cv.float_,
        cv.Optional(CONF_INVERT, default=False): cv.boolean,
        cv.Optional(CONF_TOTAL_VOLUME, default=0.0): cv.float_range(min=0.0),
        cv.Optional(CONF_RESERVE_VOLUME, default=0.0): cv.float_range(min=0.0),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    src = await cg.get_variable(config[CONF_SOURCE])
    cg.add(var.set_source(src))
    level = await sensor.new_sensor(config[CONF_LEVEL])
    cg.add(var.set_level_sensor(level))
    if CONF_VOLUME in config:
        s = await sensor.new_sensor(config[CONF_VOLUME])
        cg.add(var.set_volume_sensor(s))
    if CONF_ALMOST_EMPTY in config:
        b = await binary_sensor.new_binary_sensor(config[CONF_ALMOST_EMPTY])
        cg.add(var.set_almost_empty_sensor(b))
    if CONF_LEARNED_MIN in config:
        s = await sensor.new_sensor(config[CONF_LEARNED_MIN])
        cg.add(var.set_min_sensor(s))
    if CONF_LEARNED_MAX in config:
        s = await sensor.new_sensor(config[CONF_LEARNED_MAX])
        cg.add(var.set_max_sensor(s))
    cg.add(var.set_seed_range(config[CONF_SEED_MIN], config[CONF_SEED_MAX]))
    cg.add(var.set_invert(config[CONF_INVERT]))
    cg.add(var.set_volumes(config[CONF_TOTAL_VOLUME], config[CONF_RESERVE_VOLUME]))
