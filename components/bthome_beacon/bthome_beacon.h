#pragma once

#ifdef USE_ESP32

#include <string>

#include "esphome/core/component.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"

namespace esphome {
namespace bthome_beacon {

class BTHomeBeacon : public Component {
 public:
  void set_level_sensor(sensor::Sensor *s) { this->level_ = s; }
  void set_count_sensor(sensor::Sensor *s) { this->count_ = s; }
  void set_volume_sensor(sensor::Sensor *s) { this->volume_ = s; }
  void set_almost_empty_sensor(binary_sensor::BinarySensor *s) { this->almost_empty_ = s; }
  void set_device_name(const std::string &name) { this->name_ = name; }
  // Runtime on/off (bench diagnostics: does our own advertising starve the scanner?)
  void set_enabled(bool enabled);
  bool is_enabled() const { return this->enabled_; }

  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_BLUETOOTH; }

 protected:
  void build_and_apply_();

  sensor::Sensor *level_{nullptr};
  sensor::Sensor *count_{nullptr};
  sensor::Sensor *volume_{nullptr};
  binary_sensor::BinarySensor *almost_empty_{nullptr};
  std::string name_;
  uint8_t packet_id_{0};
  uint32_t last_update_{0};
  bool adv_started_{false};
  bool enabled_{true};
};

}  // namespace bthome_beacon
}  // namespace esphome

#endif  // USE_ESP32
