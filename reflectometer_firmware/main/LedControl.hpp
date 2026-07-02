#pragma once

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_timer.h"
#include "esp_err.h"

class LedControl {
public:
    static constexpr gpio_num_t LED_PINS[3] = {GPIO_NUM_3, GPIO_NUM_4, GPIO_NUM_5};
    static constexpr gpio_num_t PWM_PIN = GPIO_NUM_10;
    static constexpr ledc_channel_t PWM_CHANNEL = LEDC_CHANNEL_0;
    static constexpr ledc_timer_t PWM_TIMER = LEDC_TIMER_0;
    static constexpr ledc_mode_t PWM_SPEED = LEDC_LOW_SPEED_MODE;
    static constexpr uint32_t PWM_FREQ_HZ = 1000;
    static constexpr ledc_timer_bit_t PWM_RES = LEDC_TIMER_14_BIT;
    static constexpr uint32_t MAX_BRIGHTNESS = 2000; //~35mA

    void begin() {
        gpio_config_t io_conf = {};
        io_conf.intr_type = GPIO_INTR_DISABLE;
        io_conf.mode = GPIO_MODE_OUTPUT;
        io_conf.pin_bit_mask = (1ULL << LED_PINS[0]) | (1ULL << LED_PINS[1]) | (1ULL << LED_PINS[2]);
        io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
        io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
        gpio_config(&io_conf);

        for (auto pin : LED_PINS) {
            gpio_set_level(pin, 0);
        }

        ledc_timer_config_t timer_cfg = {};
        timer_cfg.speed_mode = PWM_SPEED;
        timer_cfg.duty_resolution = PWM_RES;
        timer_cfg.timer_num = PWM_TIMER;
        timer_cfg.freq_hz = PWM_FREQ_HZ;
        timer_cfg.clk_cfg = LEDC_USE_XTAL_CLK;
        ledc_timer_config(&timer_cfg);

        ledc_channel_config_t chan_cfg = {};
        chan_cfg.gpio_num = PWM_PIN;
        chan_cfg.speed_mode = PWM_SPEED;
        chan_cfg.channel = PWM_CHANNEL;
        chan_cfg.timer_sel = PWM_TIMER;
        chan_cfg.duty = 0;
        ledc_channel_config(&chan_cfg);

        esp_timer_create_args_t args = {};
        args.callback = timer_cb;
        for (int i = 0; i < 3; i++) {
            args.arg = (void*)(intptr_t)i;
            ESP_ERROR_CHECK(esp_timer_create(&args, &_timers[i]));
        }
    }

    void pulse(uint8_t led, uint32_t duration_ms, uint32_t brightness) {
        pulse_us(led, (uint64_t)duration_ms * 1000, brightness);
    }

    void pulse_us(uint8_t led, uint64_t duration_us, uint32_t brightness) {
        if (led > 2) return;
        esp_timer_stop(_timers[led]);
        ledc_set_duty(PWM_SPEED, PWM_CHANNEL, brightness);
        ledc_update_duty(PWM_SPEED, PWM_CHANNEL);
        gpio_set_level(LED_PINS[led], 1);
        esp_timer_start_once(_timers[led], duration_us);
    }

    void off(uint8_t led) {
        if (led > 2) return;
        esp_timer_stop(_timers[led]);
        gpio_set_level(LED_PINS[led], 0);
    }

    void all_off() {
        for (int i = 0; i < 3; i++) {
            esp_timer_stop(_timers[i]);
            gpio_set_level(LED_PINS[i], 0);
        }
        ledc_set_duty(PWM_SPEED, PWM_CHANNEL, 0);
        ledc_update_duty(PWM_SPEED, PWM_CHANNEL);
    }

private:
    esp_timer_handle_t _timers[3];

    static void timer_cb(void* arg) {
        uint8_t led = (uint8_t)(intptr_t)arg;
        gpio_set_level(LED_PINS[led], 0);
        ledc_set_duty(PWM_SPEED, PWM_CHANNEL, 0);
        ledc_update_duty(PWM_SPEED, PWM_CHANNEL);
    }
};
