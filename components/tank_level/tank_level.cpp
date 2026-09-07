#include "tank_level.h"

#ifdef USE_ESP32

#include <algorithm>
#include <cmath>
#include <cstring>

#include <esp_attr.h>

#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"

namespace esphome {
namespace tank_level {

static const char *const TAG = "tank_level";

// A candidate extremum must clear the learned bound by this much...
static const float MARGIN_OHM = 1.5f;
// ...and be observed this many times (once per wake cycle / 30 s) to be accepted.
static const uint8_t ACCEPT_COUNT = 5;
// Candidate forgotten after this many in-range observations (isolated spikes decay).
static const uint8_t GAP_RESET = 20;
// Below this learned span the seed range still participates in the mapping.
static const float MIN_SPAN_OHM = 25.0f;
// Cross-wake smoothing (suppresses sloshing) and persistence threshold.
static const float EMA_ALPHA = 0.35f;
static const float SAVE_DELTA_PCT = 2.0f;
static const uint32_t COUNT_GATE_MS = 30000;
// Measured level at/below this = float on its bottom stop, reserve draining blind.
static const float ALMOST_EMPTY_PCT = 2.0f;

// Short-term state in RTC slow memory: survives deep sleep, not power loss.
struct TankCalRtc {
  uint32_t magic;
  float level_ema;
  float cand_min, cand_max;
  uint8_t cand_min_n, cand_max_n;
  uint8_t cand_min_gap, cand_max_gap;
  uint8_t boot_n;
  uint8_t fault_n;
  // Median window over the last valid raw samples. Kept here so a sleeping node
  // (a few samples per wake) reaches a full window; calibration only ever looks at
  // a full-window median, never at the first sample of a boot.
  float ring[5];
  uint8_t ring_n, ring_i;
};
static const uint32_t RTC_MAGIC = 0x7AACCA1C;  // bump when the layout changes
static RTC_DATA_ATTR TankCalRtc s_rtc;  // NOLINT

void TankLevel::setup() {
  this->pref_ = global_preferences->make_preference<TankCalPersisted>(fnv1_hash("kali_tank_cal_v1"));
  if (!this->pref_.load(&this->cal_)) {
    this->cal_.learned_min = NAN;
    this->cal_.learned_max = NAN;
    this->cal_.last_good_level = NAN;
    this->cal_.flags = 0;
    ESP_LOGI(TAG, "No stored calibration — starting fresh");
  }
  if (s_rtc.magic != RTC_MAGIC) {
    memset(&s_rtc, 0, sizeof(s_rtc));
    s_rtc.magic = RTC_MAGIC;
    s_rtc.level_ema = NAN;
  }
  this->source_->add_on_state_callback([this](float x) { this->on_raw_(x); });
  this->publish_learned_();
}

void TankLevel::on_raw_(float r) {
  if (std::isnan(r) || r < this->plausible_min_ || r > this->plausible_max_) {
    if (s_rtc.fault_n < 255)
      s_rtc.fault_n++;
    if (s_rtc.fault_n == 3)
      ESP_LOGW(TAG, "Implausible readings (r=%.1f Ω) — holding last good level", r);
    // Keep the outputs fed (and thus the BTHome beacon) with the last good value.
    float lg = !std::isnan(s_rtc.level_ema) ? s_rtc.level_ema : this->cal_.last_good_level;
    if (!std::isnan(lg))
      this->publish_outputs_(lg);
    return;
  }
  s_rtc.fault_n = 0;

  s_rtc.ring[s_rtc.ring_i] = r;
  s_rtc.ring_i = (s_rtc.ring_i + 1) % 5;
  if (s_rtc.ring_n < 5)
    s_rtc.ring_n++;
  // Tiny insertion sort instead of std::sort: GCC's inlined sort trips
  // -Warray-bounds on small runtime-sized ranges.
  float tmp[5];
  const uint8_t n = std::min<uint8_t>(s_rtc.ring_n, 5);
  memcpy(tmp, s_rtc.ring, sizeof(float) * n);
  for (uint8_t a = 1; a < n; a++) {
    const float v = tmp[a];
    int8_t b = a - 1;
    while (b >= 0 && tmp[b] > v) {
      tmp[b + 1] = tmp[b];
      b--;
    }
    tmp[b + 1] = v;
  }
  const float r_med = tmp[n / 2];

  // Learn only from a full median window: a lone sample (switch-on artefact,
  // spike) can move the level a little but never the calibration.
  if (n >= 5)
    this->update_calibration_(r_med);

  float emin, emax;
  this->effective_range_(&emin, &emax);
  float lvl = 100.0f * (r_med - emin) / (emax - emin);
  if (this->invert_)
    lvl = 100.0f - lvl;
  lvl = std::fmax(0.0f, std::fmin(100.0f, lvl));
  if (std::isnan(s_rtc.level_ema)) {
    s_rtc.level_ema = lvl;
  } else {
    s_rtc.level_ema += EMA_ALPHA * (lvl - s_rtc.level_ema);
  }
  this->publish_outputs_(s_rtc.level_ema);
  this->maybe_save_(false);
}

void TankLevel::set_total_volume(float liters) {
  this->total_volume_ = std::fmax(0.0f, liters);
  ESP_LOGI(TAG, "Total volume set to %.0f L", this->total_volume_);
  this->republish_();
}

void TankLevel::set_reserve_volume(float liters) {
  this->reserve_volume_ = std::fmax(0.0f, liters);
  ESP_LOGI(TAG, "Reserve volume set to %.0f L", this->reserve_volume_);
  this->republish_();
}

void TankLevel::reset_calibration() {
  this->cal_.learned_min = NAN;
  this->cal_.learned_max = NAN;
  this->cal_.last_good_level = NAN;
  this->cal_.flags = 0;
  this->pref_.save(&this->cal_);
  global_preferences->sync();
  memset(&s_rtc, 0, sizeof(s_rtc));
  s_rtc.magic = RTC_MAGIC;
  s_rtc.level_ema = NAN;
  this->last_min_count_ms_ = 0;
  this->last_max_count_ms_ = 0;
  if (this->min_sensor_ != nullptr)
    this->min_sensor_->publish_state(NAN);
  if (this->max_sensor_ != nullptr)
    this->max_sensor_->publish_state(NAN);
  ESP_LOGW(TAG, "Calibration reset — learning the sender range from scratch");
}

void TankLevel::republish_() {
  if (!std::isnan(s_rtc.level_ema))
    this->publish_outputs_(s_rtc.level_ema);
}

void TankLevel::publish_outputs_(float measured_level) {
  // Reserve model: `measured_level` covers the float's travel only; below it the
  // pump can still draw `reserve_volume_` liters. Rescale so the published level
  // reflects true content and bottoms out at the reserve fraction, not 0 %.
  float reserve_frac = 0.0f;
  if (this->total_volume_ > 0.0f && this->reserve_volume_ > 0.0f &&
      this->reserve_volume_ < this->total_volume_) {
    reserve_frac = this->reserve_volume_ / this->total_volume_;
  }
  const float true_pct = 100.0f * reserve_frac + measured_level * (1.0f - reserve_frac);
  if (this->level_ != nullptr)
    this->level_->publish_state(true_pct);
  if (this->volume_sensor_ != nullptr && this->total_volume_ > 0.0f)
    this->volume_sensor_->publish_state(true_pct * this->total_volume_ / 100.0f);
  if (this->almost_empty_ != nullptr)
    this->almost_empty_->publish_state(measured_level <= ALMOST_EMPTY_PCT);
}

void TankLevel::update_calibration_(float r_med) {
  const uint32_t now = millis();
  const bool gate_min = this->last_min_count_ms_ == 0 || now - this->last_min_count_ms_ >= COUNT_GATE_MS;
  const bool gate_max = this->last_max_count_ms_ == 0 || now - this->last_max_count_ms_ >= COUNT_GATE_MS;

  if (this->cal_.flags == 0) {
    // Bootstrap: initialize the learned range around the first stable readings.
    if (!gate_min)
      return;
    this->last_min_count_ms_ = now;
    if (s_rtc.boot_n == 0) {
      s_rtc.cand_min = s_rtc.cand_max = r_med;
    } else {
      s_rtc.cand_min = std::fmin(s_rtc.cand_min, r_med);
      s_rtc.cand_max = std::fmax(s_rtc.cand_max, r_med);
    }
    s_rtc.boot_n++;
    if (s_rtc.boot_n >= ACCEPT_COUNT) {
      this->cal_.learned_min = s_rtc.cand_min;
      this->cal_.learned_max = s_rtc.cand_max;
      this->cal_.flags = 3;
      s_rtc.boot_n = s_rtc.cand_min_n = s_rtc.cand_max_n = 0;
      ESP_LOGI(TAG, "Calibration bootstrapped: [%.1f, %.1f] Ω", this->cal_.learned_min, this->cal_.learned_max);
      this->publish_learned_();
      this->maybe_save_(true);
    }
    return;
  }

  // New-minimum candidate: conservative — the least extreme observation wins,
  // and the range only ever expands.
  if (r_med < this->cal_.learned_min - MARGIN_OHM) {
    if (gate_min) {
      s_rtc.cand_min = s_rtc.cand_min_n == 0 ? r_med : std::fmax(s_rtc.cand_min, r_med);
      s_rtc.cand_min_n++;
      s_rtc.cand_min_gap = 0;
      this->last_min_count_ms_ = now;
      if (s_rtc.cand_min_n >= ACCEPT_COUNT) {
        this->cal_.learned_min = s_rtc.cand_min;
        s_rtc.cand_min_n = 0;
        ESP_LOGI(TAG, "Accepted new learned minimum: %.1f Ω", this->cal_.learned_min);
        this->publish_learned_();
        this->maybe_save_(true);
      }
    }
  } else if (s_rtc.cand_min_n > 0 && gate_min) {
    this->last_min_count_ms_ = now;
    if (++s_rtc.cand_min_gap >= GAP_RESET) {
      s_rtc.cand_min_n = 0;
      s_rtc.cand_min_gap = 0;
    }
  }

  // New-maximum candidate, mirrored.
  if (r_med > this->cal_.learned_max + MARGIN_OHM) {
    if (gate_max) {
      s_rtc.cand_max = s_rtc.cand_max_n == 0 ? r_med : std::fmin(s_rtc.cand_max, r_med);
      s_rtc.cand_max_n++;
      s_rtc.cand_max_gap = 0;
      this->last_max_count_ms_ = now;
      if (s_rtc.cand_max_n >= ACCEPT_COUNT) {
        this->cal_.learned_max = s_rtc.cand_max;
        s_rtc.cand_max_n = 0;
        ESP_LOGI(TAG, "Accepted new learned maximum: %.1f Ω", this->cal_.learned_max);
        this->publish_learned_();
        this->maybe_save_(true);
      }
    }
  } else if (s_rtc.cand_max_n > 0 && gate_max) {
    this->last_max_count_ms_ = now;
    if (++s_rtc.cand_max_gap >= GAP_RESET) {
      s_rtc.cand_max_n = 0;
      s_rtc.cand_max_gap = 0;
    }
  }
}

void TankLevel::effective_range_(float *out_min, float *out_max) const {
  if (this->cal_.flags != 0 && (this->cal_.learned_max - this->cal_.learned_min) >= MIN_SPAN_OHM) {
    *out_min = this->cal_.learned_min;
    *out_max = this->cal_.learned_max;
    return;
  }
  // Not (yet) enough learned span: blend with the broad seed assumptions.
  *out_min = this->cal_.flags != 0 ? std::fmin(this->cal_.learned_min, this->seed_min_) : this->seed_min_;
  *out_max = this->cal_.flags != 0 ? std::fmax(this->cal_.learned_max, this->seed_max_) : this->seed_max_;
}

void TankLevel::maybe_save_(bool force) {
  const bool level_moved =
      std::isnan(this->cal_.last_good_level) ||
      (!std::isnan(s_rtc.level_ema) && std::fabs(s_rtc.level_ema - this->cal_.last_good_level) >= SAVE_DELTA_PCT);
  if (!force && !level_moved)
    return;
  if (!std::isnan(s_rtc.level_ema))
    this->cal_.last_good_level = s_rtc.level_ema;
  this->pref_.save(&this->cal_);
  global_preferences->sync();
}

void TankLevel::publish_learned_() {
  if (this->cal_.flags == 0)
    return;
  if (this->min_sensor_ != nullptr)
    this->min_sensor_->publish_state(this->cal_.learned_min);
  if (this->max_sensor_ != nullptr)
    this->max_sensor_->publish_state(this->cal_.learned_max);
}

void TankLevel::dump_config() {
  ESP_LOGCONFIG(TAG, "Tank level calibration:");
  ESP_LOGCONFIG(TAG, "  Seed range: [%.1f, %.1f] Ω", this->seed_min_, this->seed_max_);
  ESP_LOGCONFIG(TAG, "  Plausible: [%.1f, %.1f] Ω", this->plausible_min_, this->plausible_max_);
  if (this->cal_.flags != 0) {
    ESP_LOGCONFIG(TAG, "  Learned range: [%.1f, %.1f] Ω", this->cal_.learned_min, this->cal_.learned_max);
  } else {
    ESP_LOGCONFIG(TAG, "  Learned range: none yet");
  }
  ESP_LOGCONFIG(TAG, "  Last good level: %.1f %%", this->cal_.last_good_level);
  ESP_LOGCONFIG(TAG, "  Invert: %s", this->invert_ ? "yes (low R = full)" : "no (low R = empty)");
  if (this->total_volume_ > 0.0f) {
    ESP_LOGCONFIG(TAG, "  Volume: %.0f L total, %.0f L reserve below measured 0 %%",
                  this->total_volume_, this->reserve_volume_);
  } else {
    ESP_LOGCONFIG(TAG, "  Volume model: not configured");
  }
}

}  // namespace tank_level
}  // namespace esphome

#endif  // USE_ESP32
