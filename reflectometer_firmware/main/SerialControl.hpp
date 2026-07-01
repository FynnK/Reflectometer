#pragma once

#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_err.h"
#include <cstring>
#include <cstdio>

class SerialControl {
public:
    static constexpr uart_port_t UART_NUM = UART_NUM_0;
    static constexpr int TX_PIN = GPIO_NUM_21;
    static constexpr int RX_PIN = GPIO_NUM_20;
    static constexpr int BUF_SIZE = 256;
    static constexpr uint32_t MAX_BRIGHTNESS = 5500;

    uint8_t led_intensity[3] = {0, 0, 0};

    void begin() {
        uart_config_t cfg = {};
        cfg.baud_rate = 115200;
        cfg.data_bits = UART_DATA_8_BITS;
        cfg.parity = UART_PARITY_DISABLE;
        cfg.stop_bits = UART_STOP_BITS_1;
        cfg.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
        cfg.source_clk = UART_SCLK_DEFAULT;
        ESP_ERROR_CHECK(uart_param_config(UART_NUM, &cfg));
        ESP_ERROR_CHECK(uart_set_pin(UART_NUM, TX_PIN, RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
        ESP_ERROR_CHECK(uart_driver_install(UART_NUM, BUF_SIZE, BUF_SIZE, 0, nullptr, 0));
    }

    void send_data(double reflections[3], double currents[3]) {
        char line[128];
        int len = snprintf(line, sizeof(line),
            "RED: %.3f @ %.2fmA BLUE: %.3f @ %.2fmA GREEN: %.3f @ %.2fmA\n",
            reflections[0], currents[0],
            reflections[1], currents[1],
            reflections[2], currents[2]);
        uart_write_bytes(UART_NUM, line, len);
    }

    void process_commands() {
        uint8_t data[64];
        int len = uart_read_bytes(UART_NUM, data, sizeof(data), 0);
        if (len <= 0) return;

        if (_rx_len + len >= (int)sizeof(_rx_buf) - 1) {
            _rx_len = 0;
        }
        memcpy(_rx_buf + _rx_len, data, len);
        _rx_len += len;
        _rx_buf[_rx_len] = '\0';

        char *p = _rx_buf;
        while (true) {
            char *nl = (char *)memchr(p, '\n', _rx_len - (p - _rx_buf));
            if (!nl) break;
            *nl = '\0';
            _process_line(p);
            p = nl + 1;
        }

        int remaining = _rx_len - (p - _rx_buf);
        if (remaining > 0 && p != _rx_buf) {
            memmove(_rx_buf, p, remaining);
        }
        _rx_len = remaining;
        _rx_buf[_rx_len] = '\0';
    }

    uint32_t brightness_for_led(uint8_t led) const {
        if (led > 2) return 0;
        return (uint32_t)led_intensity[led] * MAX_BRIGHTNESS / 255;
    }

private:
    char _rx_buf[128];
    int _rx_len = 0;

    void _process_line(const char *line) {
        if (strncmp(line, "SET_LED:", 8) != 0) return;

        char color = line[8];
        if (line[9] != ':') return;

        int value = 0;
        for (const char *p = line + 10; *p >= '0' && *p <= '9'; p++) {
            value = value * 10 + (*p - '0');
        }
        if (value < 0) value = 0;
        if (value > 255) value = 255;

        int idx = (color == 'R') ? 0 : (color == 'G') ? 1 : (color == 'B') ? 2 : -1;
        if (idx >= 0) {
            led_intensity[idx] = (uint8_t)value;
        }
    }
};
