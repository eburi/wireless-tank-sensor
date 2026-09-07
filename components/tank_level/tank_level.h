#pragma once

#ifdef USE_ESP32

#include "esphome/core/component.h"
#include "esphome/core/preferences.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"

namespace esphome {
namespace tank_level {

// Long-term state, persisted to NVS flash. Survives deep sleep, power cycles,
// and firmware variant swaps (bench <-> sleep).
struct TankCalPersisted {
  float learned_min;
  float learned_max;
  float last_good_level;
  uint8_t flags;  // 0 = uncalibrated, 3 = bootstrap done (both extremes tracked)
} __attribute__((packed));

class TankLevel : public Component {
 public:
  void set_source(sensor::Sensor *s) { this->source_ = s; }
  void set_level_sensor(sensor::Sensor *s) { this->level_ = s; }
  void set_volume_sensor(sensor::Sensor *s) { this->volume_sensor_ = s; }
  void set_almost_empty_sensor(binary_sensor::BinarySensor *s) { this->almost_empty_ = s; }
  void set_min_sensor(sensor::Sensor *s) { this->min_sensor_ = s; }
  void set_max_sensor(sensor::Sensor *s) { this->max_sensor_ = s; }
  // Runtime setters, driven by the persisted HA "number" entities; re-publish the
  // outputs so a changed liter figure shows immediately, not at the next sample.
  void set_total_volume(float liters);
  void set_reserve_volume(float liters);
  void set_volumes(float total, float reserve) {
    this->total_volume_ = total;
    this->reserve_volume_ = reserve;
  }
  void set_seed_range(float mn, float mx) {
    this->seed_min_ = mn;
    this->seed_max_ = mx;
  }
  void set_invert(bool inv) { this->invert_ = inv; }
  void set_plausible_range(float mn, float mx) {
    this->plausible_min_ = mn;
    this->plausible_max_ = mx;
  }
  // Forget the learned range, the RTC state and the persisted level; start over.
  void reset_calibration();

  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

 protected:
  void on_raw_(float r);
  void publish_outputs_(float measured_level);
  void republish_();
  void update_calibration_(float r_med);
  void effective_range_(float *out_min, float *out_max) const;
  void maybe_save_(bool force);
  void publish_learned_();

  sensor::Sensor *source_{nullptr};
  sensor::Sensor *level_{nullptr};
  sensor::Sensor *volume_sensor_{nullptr};
  binary_sensor::BinarySensor *almost_empty_{nullptr};
  sensor::Sensor *min_sensor_{nullptr};
  sensor::Sensor *max_sensor_{nullptr};
  float seed_min_{3.0f};
  float seed_max_{183.0f};
  bool invert_{false};
  float total_volume_{0.0f};
  float reserve_volume_{0.0f};
  float plausible_min_{1.0f};
  float plausible_max_{400.0f};

  TankCalPersisted cal_{};
  ESPPreferenceObject pref_;

  // The 5-sample median ring lives in RTC memory (see tank_level.cpp) so it
  // fills up across wake cycles on a sleeping node.
  // Rate gates: one calibration observation per boot (sleep firmware) or per
  // 30 s (bench firmware). 0 = none yet this boot.
  uint32_t last_min_count_ms_{0};
  uint32_t last_max_count_ms_{0};
};

}  // namespace tank_level
}  // namespace esphome

#endif  // USE_ESP32
