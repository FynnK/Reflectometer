#pragma once

#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_err.h"
#include <cstring>

class SerialControl {
public:
    static constexpr uart_port_t UART_NUM = UART_NUM_0;
    static constexpr int TX_PIN = GPIO_NUM_21;
    static constexpr int RX_PIN = GPIO_NUM_20;
    static constexpr int BUF_SIZE = 256;

    void begin() {
        uart_config_t cfg = {};
        cfg.baud_rate = 460800;
        cfg.data_bits = UART_DATA_8_BITS;
        cfg.parity = UART_PARITY_DISABLE;
        cfg.stop_bits = UART_STOP_BITS_1;
        cfg.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
        cfg.source_clk = UART_SCLK_DEFAULT;
        ESP_ERROR_CHECK(uart_param_config(UART_NUM, &cfg));
        ESP_ERROR_CHECK(uart_set_pin(UART_NUM, TX_PIN, RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
        ESP_ERROR_CHECK(uart_driver_install(UART_NUM, BUF_SIZE, BUF_SIZE, 0, nullptr, 0));
    }

    void send(const char *data, int len) {
        uart_write_bytes(UART_NUM, data, len);
    }

    const char *read_line() {
        uint8_t data[64];
        int len = uart_read_bytes(UART_NUM, data, sizeof(data), 0);
        if (len > 0) {
            if (_rx_len + len >= (int)sizeof(_rx_buf) - 1) _rx_len = 0;
            memcpy(_rx_buf + _rx_len, data, len);
            _rx_len += len;
            _rx_buf[_rx_len] = '\0';
        }
        if (!_rx_len) return nullptr;

        char *nl = (char *)memchr(_rx_buf, '\n', _rx_len);
        if (!nl) return nullptr;

        int line_len = nl - _rx_buf;
        int copy_len = line_len < (int)sizeof(_line_buf) - 1 ? line_len : sizeof(_line_buf) - 1;
        memcpy(_line_buf, _rx_buf, copy_len);
        _line_buf[copy_len] = '\0';

        int remaining = _rx_len - (line_len + 1);
        if (remaining > 0) {
            memmove(_rx_buf, nl + 1, remaining);
        }
        _rx_len = remaining;
        _rx_buf[_rx_len] = '\0';
        return _line_buf;
    }

private:
    char _rx_buf[256];
    char _line_buf[256];
    int _rx_len = 0;
};
