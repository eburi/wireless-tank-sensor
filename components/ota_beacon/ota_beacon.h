#pragma once

#ifdef USE_ESP32

#include <array>

#include <esp_gap_ble_api.h>

#include "esphome/core/component.h"

namespace esphome {
namespace ota_beacon {

// The trigger is an iBeacon frame. The sensor matches on major/minor (byte-order
// unambiguous); the UUID is for Home Assistant's iBeacon integration to display.
static const uint16_t MAJOR = 0x4B4F;  // "KO"
static const uint8_t MINOR_HI = 0x54;  // "T" — minor = 0x54<target>

class OtaBeacon : public Component {
 public:
  void set_uuid(const std::array<uint8_t, 16> &u) { this->uuid_ = u; }
  void set_safety_timeout(uint32_t ms) { this->safety_timeout_ = ms; }

  // target = tank number carried in the minor's low byte; 0 addresses every tank.
  // Starting while another target is on air switches over to the new one.
  void start(uint8_t target);
  void stop();
  bool is_advertising() const { return this->advertising_; }
  bool is_advertising(uint8_t target) const { return this->advertising_ && this->target_ == target; }
  uint8_t active_target() const { return this->target_; }

  void loop() override;
  void dump_config() override;
  // The ESP-IDF calls only queue the request; the controller's verdict arrives
  // asynchronously as a GAP event. A failure is logged as a warning.
  void gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param);
  float get_setup_priority() const override { return setup_priority::AFTER_BLUETOOTH; }

 protected:
  std::array<uint8_t, 16> uuid_{};
  uint8_t target_{0};
  uint32_t safety_timeout_{360000};
  bool advertising_{false};
  uint32_t started_ms_{0};
};

}  // namespace ota_beacon
}  // namespace esphome

#endif  // USE_ESP32
