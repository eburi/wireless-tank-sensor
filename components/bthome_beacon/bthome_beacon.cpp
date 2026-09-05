#include "bthome_beacon.h"

#ifdef USE_ESP32

#include <cmath>
#include <cstring>

#include <esp_gap_ble_api.h>

#include "esphome/components/esp32_ble/ble.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome {
namespace bthome_beacon {

static const char *const TAG = "bthome_beacon";

// Non-connectable beacon, ~200-260 ms advertising interval (units of 0.625 ms).
static esp_ble_adv_params_t adv_params = {
    .adv_int_min = 0x0140,
    .adv_int_max = 0x01A0,
    .adv_type = ADV_TYPE_NONCONN_IND,
    .own_addr_type = BLE_ADDR_TYPE_PUBLIC,
    .peer_addr = {0},
    .peer_addr_type = BLE_ADDR_TYPE_PUBLIC,
    .channel_map = ADV_CHNL_ALL,
    .adv_filter_policy = ADV_FILTER_ALLOW_SCAN_ANY_CON_ANY,
};

void BTHomeBeacon::set_enabled(bool enabled) {
  this->enabled_ = enabled;
  if (!enabled && this->adv_started_) {
    esp_ble_gap_stop_advertising();
    this->adv_started_ = false;
    ESP_LOGI(TAG, "BTHome advertising stopped");
  }
}

void BTHomeBeacon::loop() {
  if (!this->enabled_)
    return;
  if (esp32_ble::global_ble == nullptr || !esp32_ble::global_ble->is_active())
    return;
  const uint32_t now = millis();
  if (this->adv_started_ && now - this->last_update_ < 1000)
    return;
  this->last_update_ = now;
  this->build_and_apply_();
}

void BTHomeBeacon::build_and_apply_() {
  uint8_t adv[31];
  size_t i = 0;

  // AD: Flags (general discoverable, BR/EDR unsupported)
  adv[i++] = 0x02;
  adv[i++] = 0x01;
  adv[i++] = 0x06;

  // AD: Service Data, 16-bit UUID 0xFCD2 (BTHome v2, unencrypted, regular updates).
  // Objects must be sorted by ascending object id.
  const size_t len_pos = i;
  adv[i++] = 0x00;  // length, patched below
  adv[i++] = 0x16;
  adv[i++] = 0xD2;
  adv[i++] = 0xFC;
  adv[i++] = 0x40;  // device info: BTHome version 2
  adv[i++] = 0x00;  // object: packet id
  adv[i++] = this->packet_id_++;
  if (this->almost_empty_ != nullptr && this->almost_empty_->has_state()) {
    adv[i++] = 0x26;  // object: problem, binary — "almost empty, draining reserve"
    adv[i++] = this->almost_empty_->state ? 0x01 : 0x00;
  }
  if (this->level_ != nullptr && !std::isnan(this->level_->state)) {
    const float clamped = std::fmax(0.0f, std::fmin(100.0f, this->level_->state));
    adv[i++] = 0x2F;  // object: moisture, uint8, %
    adv[i++] = (uint8_t) lroundf(clamped);
  }
  if (this->count_ != nullptr && !std::isnan(this->count_->state)) {
    const float scaled = std::fmax(0.0f, std::fmin(65535.0f, this->count_->state * 10.0f));
    const auto c = (uint16_t) lroundf(scaled);
    adv[i++] = 0x3D;  // object: count, uint16 — resistance in tenths of an ohm
    adv[i++] = (uint8_t) (c & 0xFF);
    adv[i++] = (uint8_t) (c >> 8);
  }
  if (this->volume_ != nullptr && !std::isnan(this->volume_->state)) {
    const float scaled = std::fmax(0.0f, std::fmin(6553.5f, this->volume_->state)) * 10.0f;
    const auto v = (uint16_t) lroundf(scaled);
    adv[i++] = 0x47;  // object: volume, uint16, 0.1 L
    adv[i++] = (uint8_t) (v & 0xFF);
    adv[i++] = (uint8_t) (v >> 8);
  }
  adv[len_pos] = (uint8_t) (i - len_pos - 1);

  // AD: Complete Local Name
  if (!this->name_.empty() && i + 2 + this->name_.size() <= sizeof(adv)) {
    adv[i++] = (uint8_t) (this->name_.size() + 1);
    adv[i++] = 0x09;
    std::memcpy(&adv[i], this->name_.data(), this->name_.size());
    i += this->name_.size();
  }

  esp_err_t err = esp_ble_gap_config_adv_data_raw(adv, i);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "esp_ble_gap_config_adv_data_raw failed: %d", err);
    return;
  }
  if (!this->adv_started_) {
    err = esp_ble_gap_start_advertising(&adv_params);
    if (err != ESP_OK) {
      ESP_LOGW(TAG, "esp_ble_gap_start_advertising failed: %d", err);
      return;
    }
    this->adv_started_ = true;
    ESP_LOGI(TAG, "BTHome advertising started as '%s'", this->name_.c_str());
  }
}

void BTHomeBeacon::dump_config() {
  ESP_LOGCONFIG(TAG, "BTHome beacon:");
  ESP_LOGCONFIG(TAG, "  Name: %s", this->name_.c_str());
  ESP_LOGCONFIG(TAG, "  Advertising: %s", this->adv_started_ ? "yes" : "not yet");
}

}  // namespace bthome_beacon
}  // namespace esphome

#endif  // USE_ESP32
