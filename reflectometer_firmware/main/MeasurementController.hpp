#pragma once

#include <cstdlib>
#include "Ads131m02.hpp"
#include "LedControl.hpp"
#include "Protocol.hpp"

class MeasurementController {
public:
    enum State { IDLE, MEASURING, MONITORING };
    enum Mode { CONTINUOUS, SINGLE };

    struct RawBlock {
        const int32_t *ch0 = nullptr;
        const int32_t *ch1 = nullptr;
        int presamples = 0;
        int samples = 0;
        int total = 0; // presamples + samples (capped at MAX_SAMPLES)
    };

    void begin(Ads131m02 &adc) {
        _apply_osr(adc, _config.osr);
        _update_selected();
    }

    void start(Mode mode) {
        _state = MEASURING;
        _mode = mode;
        _current_in_selected = 0;
        for (int i = 0; i < 3; i++) {
            _raw_counts[i] = 0;
            _dark_counts[i] = 0;
            _light_counts[i] = 0;
        }
    }

    void stop() {
        _state = IDLE;
        _current_in_selected = 0;
    }

    void start_monitoring() { _monitor_active = true; }

    void stop_monitoring() { _monitor_active = false; }

    bool is_monitor_active() const { return _monitor_active; }

    const char* get_status() const {
        if (_state == MEASURING) return "measuring";
        if (_monitor_active) return "monitoring";
        return "idle";
    }

    int update_monitor(Ads131m02 &adc, int32_t *ch0, int32_t *ch1, int max) {
        if (!_monitor_active) return 0;
        int count = 0;
        while (count < max) {
            auto s = adc.sample();
            ch0[count] = s.getCh0();
            ch1[count] = s.getCh1();
            count++;
        }
        return count;
    }

    State get_state() const { return _state; }
    Mode get_mode() const { return _mode; }

    Config get_config() const { return _config; }

    void set_config(const Config &cfg, Ads131m02 &adc) {
        if (cfg.osr != _config.osr) {
            _apply_osr(adc, cfg.osr);
        }
        bool channels_changed = cfg.channels != _config.channels;
        _config = cfg;
        if (channels_changed) _update_selected();
    }

    bool update(Ads131m02 &adc, LedControl &leds) {
        if (_state != MEASURING) return false;
        if (_selected_count == 0) { _state = IDLE; return false; }

        // Zero unselected channels to avoid stale data
        for (int i = 0; i < 3; i++) {
            bool selected = false;
            for (int j = 0; j < _selected_count; j++) {
                if (_selected_leds[j] == i) { selected = true; break; }
            }
            if (!selected) {
                _reflections[i] = 0.0;
                _currents[i] = 0.0;
            }
        }

        int led = _selected_leds[_current_in_selected];
        leds.all_off();

        adc.software_sync();
        for (int i = 0; i < _config.deadtime; i++) adc.sample();

        int64_t sum_ch0 = 0, sum_ch1 = 0;
        int dark_count = 0;
        for (int i = 0; i < _config.presamples; i++) {
            auto s = adc.sample();
            sum_ch0 += s.getCh0();
            sum_ch1 += s.getCh1();
            if (dark_count < MAX_SAMPLES) {
                _ch0_pool[led][dark_count] = s.getCh0();
                _ch1_pool[led][dark_count] = s.getCh1();
                dark_count++;
            }
        }
        int32_t ch0_off = dark_count > 0 ? sum_ch0 / dark_count : 0;
        int32_t ch1_off = dark_count > 0 ? sum_ch1 / dark_count : 0;

        adc.software_sync();
        for (int i = 0; i < 3; i++) adc.sample();

        int osr_value = 128 << _config.osr;
        int sample_time_us = osr_value / 2;
        int settle_samples = _config.deadtime;
        int actual_light_target = _config.samples > 0 ? _config.samples : 1;
        int pulse_duration_us = (settle_samples + actual_light_target + 1) * sample_time_us;

        uint32_t scaled = (uint32_t)_config.brightness[led] * LedControl::MAX_BRIGHTNESS / 2000;
        leds.pulse_us(led, pulse_duration_us, scaled);

        for (int i = 0; i < settle_samples; i++) adc.sample();

        sum_ch0 = 0; sum_ch1 = 0;
        int light_count = 0;
        for (int i = 0; i < actual_light_target; i++) {
            auto s = adc.sample();
            sum_ch0 += s.getCh0();
            sum_ch1 += s.getCh1();
            if (dark_count + light_count < MAX_SAMPLES) {
                _ch0_pool[led][dark_count + light_count] = s.getCh0();
                _ch1_pool[led][dark_count + light_count] = s.getCh1();
                light_count++;
            }
        }

        int32_t ch0_res = light_count > 0 ? llabs((sum_ch0 / light_count) - ch0_off) : 0;
        int32_t ch1_res = light_count > 0 ? llabs((sum_ch1 / light_count) - ch1_off) : 0;
        _reflections[led] = (ch0_res != 0) ? (double)ch1_res / ch0_res : 0.0;
        _currents[led] = (ch0_res / 8388608.0) * (1.2 / 10.0) * 1000.0;

        _dark_counts[led] = dark_count;
        _light_counts[led] = light_count;
        _raw_counts[led] = dark_count + light_count;

        _current_in_selected++;
        if (_current_in_selected >= _selected_count) {
            _current_in_selected = 0;
            for (int i = 0; i < 3; i++) {
                _raw_blocks[i] = {_ch0_pool[i], _ch1_pool[i],
                                  _dark_counts[i], _light_counts[i], _raw_counts[i]};
            }
            _cycle_ready = true;
            if (_mode == SINGLE) {
                _state = IDLE;
            }
            return true;
        }
        return false;
    }

    const double *get_reflections() const { return _reflections; }
    const double *get_currents() const { return _currents; }

    const RawBlock *get_raw_blocks() const {
        return (_state == IDLE || _cycle_ready) ? _raw_blocks : nullptr;
    }

    void consume_raw_blocks() {
        _cycle_ready = false;
    }

private:
    static constexpr int MAX_SAMPLES = 2048;

    State _state = IDLE;
    Mode _mode = CONTINUOUS;
    Config _config;
    int _current_in_selected = 0;
    int _selected_leds[3] = {};
    int _selected_count = 0;

    double _reflections[3] = {};
    double _currents[3] = {};

    int32_t _ch0_pool[3][MAX_SAMPLES];
    int32_t _ch1_pool[3][MAX_SAMPLES];
    int _dark_counts[3] = {};
    int _light_counts[3] = {};
    int _raw_counts[3] = {};
    bool _cycle_ready = false;
    bool _monitor_active = false;
    RawBlock _raw_blocks[3] = {};

    void _update_selected() {
        _selected_count = 0;
        for (int i = 0; i < 3; i++) {
            if (_config.channels & (1 << i)) {
                _selected_leds[_selected_count++] = i;
            }
        }
        if (_current_in_selected >= _selected_count) _current_in_selected = 0;
    }

    void _apply_osr(Ads131m02 &adc, int osr) {
        adc.write_register(Ads131m02::REG_CLOCK,
            Ads131m02::CLOCK_CH0_EN | Ads131m02::CLOCK_CH1_EN |
            Ads131m02::CLOCK_OSR(osr) | Ads131m02::CLOCK_PWR_HR);
    }
};