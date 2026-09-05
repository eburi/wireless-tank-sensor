#include "ota_beacon.h"

#ifdef USE_ESP32

#include <esp_gap_ble_api.h>

#include "esphome/components/esp32_ble/ble.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome {
namespace ota_beacon {

static const char *const TAG = "ota_beacon";

static esp_ble_adv_params_t adv_params = {
    .adv_int_min = 0x00A0,  // ~100 ms — advertise briskly so a wake window catches it
    .adv_int_max = 0x00F0,
    .adv_type = ADV_TYPE_NONCONN_IND,
    .own_addr_type = BLE_ADDR_TYPE_PUBLIC,
    .peer_addr = {0},
    .peer_addr_type = BLE_ADDR_TYPE_PUBLIC,
    .channel_map = ADV_CHNL_ALL,
    .adv_filter_policy = ADV_FILTER_ALLOW_SCAN_ANY_CON_ANY,
};

void OtaBeacon::gap_event_handler(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {
  // esp_ble_gap_* only queue the request; the controller answers asynchronously.
  // Status 0 = accepted. Anything else means "not on air" and must not stay silent.
  const char *what;
  int status;
  switch (event) {
    case ESP_GAP_BLE_ADV_DATA_RAW_SET_COMPLETE_EVT:
      what = "adv data set";
      status = (int) param->adv_data_raw_cmpl.status;
      break;
    case ESP_GAP_BLE_ADV_START_COMPLETE_EVT:
      what = "adv start";
      status = (int) param->adv_start_cmpl.status;
      break;
    case ESP_GAP_BLE_ADV_STOP_COMPLETE_EVT:
      what = "adv stop";
      status = (int) param->adv_stop_cmpl.status;
      break;
    default:
      return;
  }
  if (status == 0) {
    ESP_LOGD(TAG, "GAP: %s ok", what);
  } else {
    ESP_LOGW(TAG, "GAP: %s FAILED, status %d — trigger is not on air", what, status);
  }
}

void OtaBeacon::start(uint8_t target) {
  if (esp32_ble::global_ble == nullptr || !esp32_ble::global_ble->is_active()) {
    ESP_LOGW(TAG, "BLE stack not ready — cannot start trigger");
    return;
  }
  if (this->advertising_) {
    // Switch target: stop the running advertisement first (the controller
    // rejects a start while one is active).
    esp_ble_gap_stop_advertising();
    this->advertising_ = false;
  }
  this->target_ = target;
  // Standard iBeacon frame: ESPHome's tracker parses it natively and Home
  // Assistant's iBeacon integration shows it while it is on air.
  uint8_t adv[30];
  size_t i = 0;
  adv[i++] = 0x02;  // flags
  adv[i++] = 0x01;
  adv[i++] = 0x06;
  adv[i++] = 0x1A;  // manufacturer data: type(1) + company(2) + 0x02 0x15 + 21
  adv[i++] = 0xFF;
  adv[i++] = 0x4C;  // Apple company id, little-endian
  adv[i++] = 0x00;
  adv[i++] = 0x02;  // iBeacon type
  adv[i++] = 0x15;  // iBeacon payload length
  for (uint8_t b : this->uuid_)
    adv[i++] = b;
  adv[i++] = (uint8_t) (MAJOR >> 8);  // major, big-endian
  adv[i++] = (uint8_t) (MAJOR & 0xFF);
  adv[i++] = MINOR_HI;  // minor: 'T' + target, big-endian
  adv[i++] = this->target_;
  adv[i++] = 0xC5;  // measured power at 1 m (-59 dBm), informational

  esp_err_t err = esp_ble_gap_config_adv_data_raw(adv, i);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "config_adv_data_raw failed: %d", err);
    return;
  }
  err = esp_ble_gap_start_advertising(&adv_params);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "start_advertising failed: %d", err);
    return;
  }
  this->advertising_ = true;
  this->started_ms_ = millis();
  ESP_LOGI(TAG, "OTA trigger advertising (target %u%s)", this->target_, this->target_ == 0 ? " = all tanks" : "");
}

void OtaBeacon::stop() {
  if (!this->advertising_)
    return;
  esp_ble_gap_stop_advertising();
  this->advertising_ = false;
  ESP_LOGI(TAG, "OTA trigger stopped (target %u)", this->target_);
}

void OtaBeacon::loop() {
  if (this->advertising_ && millis() - this->started_ms_ > this->safety_timeout_) {
    ESP_LOGW(TAG, "Safety timeout reached — stopping trigger");
    this->stop();
  }
}

void OtaBeacon::dump_config() {
  ESP_LOGCONFIG(TAG, "OTA trigger beacon (iBeacon):");
  ESP_LOGCONFIG(TAG, "  Major 0x%04X, minor 0x%02X<target> (0 = all tanks)", MAJOR, MINOR_HI);
  ESP_LOGCONFIG(TAG, "  Safety timeout: %u s", (unsigned) (this->safety_timeout_ / 1000));
}

}  // namespace ota_beacon
}  // namespace esphome

#endif  // USE_ESP32
