#include <cstdint>
#include <stdio.h>
#include <cstring>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"

#include "Ads131m02.hpp"
#include "LedControl.hpp"
#include "ClockGenerator.hpp"

static const char TAG[] = "main";

const double ADC_FULL_SCALE = 8388608.0; // 2^23 for 24-bit ADC
const double ADC_VREF = 1.2;             // 1.2V reference
const double R_SENSE = 10.0;             // 10 Ohm sense resistor

Ads131m02 adc;
LedControl leds;

extern "C" void app_main(void) {
    // 1. Initialize Hardware Components
    generate_adc_mclk();

    adc.init_pins();
    vTaskDelay(pdMS_TO_TICKS(100));
    adc.init_spi();

    // 2. Configure ADC Registers
    adc.send_software_reset();
    vTaskDelay(pdMS_TO_TICKS(10));
    adc.write_register(Ads131m02::REG_MODE, Ads131m02::MODE_WLENGTH_24);
    adc.write_register(Ads131m02::REG_CLOCK, Ads131m02::CLOCK_CH0_EN | Ads131m02::CLOCK_CH1_EN | Ads131m02::CLOCK_OSR(Ads131m02::OSR_4096) | Ads131m02::CLOCK_PWR_HR);

    leds.begin();

    uint32_t intensity = 1000;
    int32_t ch0_offset;
    int32_t ch1_offset;
    uint8_t num_presamples = 80;
    uint8_t num_samples = 160;
    double reflection[3] = {};
    double current[3] = {};


    ESP_LOGI(TAG, "Starting synchronous pulse polling loop in main task...");

    while (1) {
        for(int led = 0; led < 3; led++){
            // Resynchronize internal Sinc3 filters cleanly via SPI command
            adc.software_sync();
            for(int i = 0; i < 3; i++){
                adc.sample();
            }

            int64_t sum_ch0 = 0;
            int64_t sum_ch1 = 0;
            for(int i = 0; i < num_presamples; i++){
                sum_ch0 += adc.sample().getCh0();
                sum_ch1 += adc.sample().getCh1();
            }
            ch0_offset = sum_ch0 / num_presamples;
            ch1_offset = sum_ch1 / num_presamples;

            adc.software_sync();
            leds.pulse(led, num_samples + 10, intensity);
            for(int i = 0; i < 3; i++){
                adc.sample();
            }

            sum_ch0 = 0;
            sum_ch1 = 0;
            for(int i = 0; i < num_samples; i++){
                sum_ch0 += adc.sample().getCh0();
                sum_ch1 += adc.sample().getCh1();
            }
            int32_t ch0_res = llabs((sum_ch0 / num_samples) - ch0_offset);
            int32_t ch1_res = llabs((sum_ch1 / num_samples) - ch1_offset);

            reflection[led] = (double)ch1_res / ch0_res;
            current[led] = (ch0_res / ADC_FULL_SCALE) * (ADC_VREF / R_SENSE) * 1000;

            vTaskDelay(10);

            //double led_current = (avg_counts / ADC_FULL_SCALE) * (ADC_VREF / R_SENSE);
            //double ch1_voltage = (ch1_avg_counts / ADC_FULL_SCALE) * ADC_VREF;
        }

        ESP_LOGI(TAG, "RED: %lf @ %.2f mA | BLUE: %lf @ %.2f mA | GREEN: %lf @ %.2f mA",reflection[0], current[0], reflection[1], current[1], reflection[2], current[2]);
    }
}
