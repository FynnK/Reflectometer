#pragma once

#include "driver/ledc.h"
#include "esp_log.h"

#define PIN_CLKIN_GEN  GPIO_NUM_6

static const char CLK_TAG[] = "clkgen";

static void generate_adc_mclk() {
    ledc_timer_config_t ledc_timer = {};
    ledc_timer.speed_mode       = LEDC_LOW_SPEED_MODE;
    ledc_timer.duty_resolution  = LEDC_TIMER_1_BIT;
    ledc_timer.timer_num        = LEDC_TIMER_1;
    ledc_timer.freq_hz          = 8000000;
    ledc_timer.clk_cfg          = LEDC_USE_XTAL_CLK;
    ESP_ERROR_CHECK(ledc_timer_config(&ledc_timer));

    ledc_channel_config_t ledc_channel = {};
    ledc_channel.speed_mode     = LEDC_LOW_SPEED_MODE;
    ledc_channel.channel        = LEDC_CHANNEL_1;
    ledc_channel.timer_sel      = LEDC_TIMER_1;
    ledc_channel.intr_type      = LEDC_INTR_DISABLE;
    ledc_channel.gpio_num       = PIN_CLKIN_GEN;
    ledc_channel.duty           = 1;
    ledc_channel.hpoint         = 0;
    ESP_ERROR_CHECK(ledc_channel_config(&ledc_channel));

    ESP_LOGI(CLK_TAG, "ADC MCLK on GPIO%d @ 8.192 MHz", PIN_CLKIN_GEN);
}
