#include <cstdint>
#include <stdio.h>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"

#include "Ads131m02.hpp"
#include "LedControl.hpp"
#include "ClockGenerator.hpp"
#include "SerialControl.hpp"
#include "Protocol.hpp"
#include "MeasurementController.hpp"

Ads131m02 adc;
LedControl leds;
SerialControl serial;
MeasurementController controller;

static void handle_cmd(const Command &cmd) {
    char buf[256];
    int len = 0;

    switch (cmd.type) {
        case Command::START: {
            controller.stop_monitoring();
            Config cfg = controller.get_config();
            if (cmd.osr >= 0) cfg.osr = cmd.osr;
            if (cmd.presamples >= 1) cfg.presamples = cmd.presamples;
            if (cmd.samples >= 1) cfg.samples = cmd.samples;
            if (cmd.pulse_ms >= 5) cfg.pulse_ms = cmd.pulse_ms;
            if (cmd.channels >= 0) cfg.channels = cmd.channels;
            if (cmd.deadtime >= 1) cfg.deadtime = cmd.deadtime;
            if (cmd.brightness_r >= 0) cfg.brightness[0] = cmd.brightness_r;
            if (cmd.brightness_b >= 0) cfg.brightness[1] = cmd.brightness_b;
            if (cmd.brightness_g >= 0) cfg.brightness[2] = cmd.brightness_g;
            if (cmd.send_raw >= 0) cfg.send_raw = cmd.send_raw;
            controller.set_config(cfg, adc);

            auto mode = (strcmp(cmd.mode, "single") == 0)
                        ? MeasurementController::SINGLE
                        : MeasurementController::CONTINUOUS;
            controller.start(mode);
            len = Protocol::format_status(buf, sizeof(buf), controller.get_status());
            serial.send(buf, len);
            break;
        }
        case Command::STOP:
            controller.stop_monitoring();
            controller.stop();
            leds.all_off();
            len = Protocol::format_status(buf, sizeof(buf), controller.get_status());
            serial.send(buf, len);
            break;
        case Command::SET: {
            Config cfg = controller.get_config();
            if (cmd.osr >= 0) cfg.osr = cmd.osr;
            if (cmd.presamples >= 1) cfg.presamples = cmd.presamples;
            if (cmd.samples >= 1) cfg.samples = cmd.samples;
            if (cmd.pulse_ms >= 5) cfg.pulse_ms = cmd.pulse_ms;
            if (cmd.channels >= 0) cfg.channels = cmd.channels;
            if (cmd.deadtime >= 1) cfg.deadtime = cmd.deadtime;
            if (cmd.brightness_r >= 0) cfg.brightness[0] = cmd.brightness_r;
            if (cmd.brightness_b >= 0) cfg.brightness[1] = cmd.brightness_b;
            if (cmd.brightness_g >= 0) cfg.brightness[2] = cmd.brightness_g;
            if (cmd.send_raw >= 0) cfg.send_raw = cmd.send_raw;
            controller.set_config(cfg, adc);
            len = Protocol::format_config(buf, sizeof(buf), cfg);
            serial.send(buf, len);
            break;
        }
        case Command::CONFIG: {
            Config cfg = controller.get_config();
            len = Protocol::format_config(buf, sizeof(buf), cfg);
            serial.send(buf, len);
            break;
        }
        case Command::MONITOR:
            if (cmd.enable) {
                controller.start_monitoring();
                len = Protocol::format_status(buf, sizeof(buf), controller.get_status());
            } else {
                controller.stop_monitoring();
                len = Protocol::format_status(buf, sizeof(buf), controller.get_status());
            }
            serial.send(buf, len);
            break;
        case Command::NONE: {
            len = Protocol::format_error(buf, sizeof(buf), "unrecognized command");
            serial.send(buf, len);
            break;
        }
    }
}

extern "C" void app_main(void) {
    generate_adc_mclk();

    adc.init_pins();
    vTaskDelay(pdMS_TO_TICKS(100));
    adc.init_spi();

    adc.send_software_reset();
    vTaskDelay(pdMS_TO_TICKS(10));
    adc.write_register(Ads131m02::REG_MODE, Ads131m02::MODE_WLENGTH_24);

    leds.begin();
    serial.begin();
    controller.begin(adc);

    char buf[256];
    static char rawbuf[65536];
    int len = Protocol::format_status(buf, sizeof(buf), "idle");
    serial.send(buf, len);

    while (1) {
        const char *line;
        while ((line = serial.read_line()) != nullptr) {
            handle_cmd(Protocol::parse(line));
        }

        if (controller.is_monitor_active() && controller.get_state() != MeasurementController::MEASURING) {
            static int32_t mon_ch0[20], mon_ch1[20];
            int n = controller.update_monitor(adc, mon_ch0, mon_ch1, 20);
            if (n > 0) {
                static char monbuf[8192];
                len = Protocol::format_monitor(monbuf, sizeof(monbuf), mon_ch0, mon_ch1, n);
                serial.send(monbuf, len);
            }
        }

        if (controller.get_state() == MeasurementController::MEASURING) {
            bool cycle_done = controller.update(adc, leds);
            if (cycle_done) {
                len = Protocol::format_data(buf, sizeof(buf),
                    controller.get_reflections(), controller.get_currents());
                serial.send(buf, len);

                auto blocks = controller.get_raw_blocks();
                bool send_raw = controller.get_config().send_raw;
                bool mon_active = controller.is_monitor_active();
                if (blocks && send_raw) {
                    for (int led = 0; led < 3; led++) {
                        if (blocks[led].total > 0) {
                            len = Protocol::format_data_raw(rawbuf, sizeof(rawbuf), led,
                                blocks[led].ch0, blocks[led].ch1,
                                blocks[led].presamples, blocks[led].total);
                            serial.send(rawbuf, len);

                            if (mon_active) {
                                static char monbuf[8192];
                                len = Protocol::format_monitor(monbuf, sizeof(monbuf),
                                    blocks[led].ch0, blocks[led].ch1, blocks[led].total);
                                serial.send(monbuf, len);
                            }
                        }
                    }
                    controller.consume_raw_blocks();
                }

                if (controller.get_mode() == MeasurementController::SINGLE) {
                    if (!send_raw && blocks) {
                        for (int led = 0; led < 3; led++) {
                            if (blocks[led].total > 0) {
                                len = Protocol::format_raw(rawbuf, sizeof(rawbuf), led,
                                    blocks[led].ch0, blocks[led].ch1, blocks[led].total);
                                serial.send(rawbuf, len);

                                if (mon_active) {
                                    static char monbuf[8192];
                                    len = Protocol::format_monitor(monbuf, sizeof(monbuf),
                                        blocks[led].ch0, blocks[led].ch1, blocks[led].total);
                                    serial.send(monbuf, len);
                                }
                            }
                        }
                    }
                    len = Protocol::format_status(buf, sizeof(buf), controller.get_status());
                    serial.send(buf, len);
                }
            }
        }

        vTaskDelay(1);
    }
}
