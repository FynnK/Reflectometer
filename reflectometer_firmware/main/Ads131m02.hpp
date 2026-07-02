#pragma once

#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdint>
#include <cstring>

#include "Sample.hpp"
#include "esp_timer.h"


class Ads131m02 {
public:
    static constexpr gpio_num_t PIN_MOSI = GPIO_NUM_2;
    static constexpr gpio_num_t PIN_MISO = GPIO_NUM_7;
    static constexpr gpio_num_t PIN_SCK  = GPIO_NUM_8;
    static constexpr gpio_num_t PIN_CS   = GPIO_NUM_9;
    static constexpr gpio_num_t PIN_DRDY = GPIO_NUM_NC;

    static constexpr int ADS_WORD_SIZE_BYTES = 3;
    static constexpr int NUM_WORDS           = 4;
    static constexpr int NUM_CHANNELS        = 2;
    static constexpr int FRAME_BYTES         = NUM_WORDS * ADS_WORD_SIZE_BYTES; // 12

    // ---- Commands (Table 8-11) ----
    static constexpr uint16_t CMD_NULL    = 0x0000;
    static constexpr uint16_t CMD_RESET   = 0x0011;
    static constexpr uint16_t CMD_STANDBY = 0x0022;
    static constexpr uint16_t CMD_WAKEUP  = 0x0033;
    static constexpr uint16_t CMD_LOCK    = 0x0555;
    static constexpr uint16_t CMD_UNLOCK  = 0x0666;

    // ---- Register Addresses (Table 8-12) ----
    enum RegAddr : uint8_t {
        REG_ID           = 0x00,
        REG_STATUS       = 0x01,
        REG_MODE         = 0x02,
        REG_CLOCK        = 0x03,
        REG_GAIN         = 0x04,
        REG_CFG          = 0x06,
        REG_THRSHLD_MSB  = 0x07,
        REG_THRSHLD_LSB  = 0x08,
        REG_CH0_CFG      = 0x09,
        REG_CH0_OCAL_MSB = 0x0A,
        REG_CH0_OCAL_LSB = 0x0B,
        REG_CH0_GCAL_MSB = 0x0C,
        REG_CH0_GCAL_LSB = 0x0D,
        REG_CH1_CFG      = 0x0E,
        REG_CH1_OCAL_MSB = 0x0F,
        REG_CH1_OCAL_LSB = 0x10,
        REG_CH1_GCAL_MSB = 0x11,
        REG_CH1_GCAL_LSB = 0x12,
        REG_REGMAP_CRC   = 0x3E,
    };

    // ---- MODE register (0x02) bit positions (Figure 8-28) ----
    static constexpr uint16_t MODE_REGCRC_EN  = 1 << 13;
    static constexpr uint16_t MODE_RX_CRC_EN  = 1 << 12;
    static constexpr uint16_t MODE_CRC_TYPE   = 1 << 11;
    static constexpr uint16_t MODE_RESET      = 1 << 10;
    static constexpr uint16_t MODE_WLENGTH_16 = 0 << 8;
    static constexpr uint16_t MODE_WLENGTH_24 = 1 << 8;
    static constexpr uint16_t MODE_WLENGTH_32Z = 2 << 8;
    static constexpr uint16_t MODE_WLENGTH_32SE = 3 << 8;
    static constexpr uint16_t MODE_TIMEOUT    = 1 << 4;
    static constexpr uint16_t MODE_DRDY_SEL_MOST_LAGGING = 0;
    static constexpr uint16_t MODE_DRDY_SEL_ANY    = 1;
    static constexpr uint16_t MODE_DRDY_SEL_MOST_LEADING = 2;
    static constexpr uint16_t MODE_DRDY_HIZ   = 1 << 1;
    static constexpr uint16_t MODE_DRDY_FMT   = 1 << 0;

    // ---- STATUS register (0x01) bit positions (Figure 8-27) ----
    static constexpr uint16_t STATUS_LOCK     = 1 << 15;
    static constexpr uint16_t STATUS_F_RESYNC = 1 << 14;
    static constexpr uint16_t STATUS_REGMAP   = 1 << 13;
    static constexpr uint16_t STATUS_CRC_ERR  = 1 << 12;
    static constexpr uint16_t STATUS_CRC_TYPE = 1 << 11;
    static constexpr uint16_t STATUS_RESET    = 1 << 10;
    static constexpr uint16_t STATUS_DRDY1    = 1 << 1;
    static constexpr uint16_t STATUS_DRDY0    = 1 << 0;

    // ---- CLOCK register (0x03) bit positions (Figure 8-29) ----
    static constexpr uint16_t CLOCK_CH1_EN    = 1 << 9;
    static constexpr uint16_t CLOCK_CH0_EN    = 1 << 8;
    static constexpr uint16_t CLOCK_TBM       = 1 << 5;
    static constexpr uint16_t CLOCK_OSR(uint8_t osr) { return (osr & 0x7) << 2; }
    static constexpr uint16_t CLOCK_PWR_VLP   = 0;
    static constexpr uint16_t CLOCK_PWR_LP    = 1;
    static constexpr uint16_t CLOCK_PWR_HR    = 2;

    static constexpr uint16_t OSR_128    = 0;
    static constexpr uint16_t OSR_256    = 1;
    static constexpr uint16_t OSR_512    = 2;
    static constexpr uint16_t OSR_1024   = 3;
    static constexpr uint16_t OSR_2048   = 4;
    static constexpr uint16_t OSR_4096   = 5;
    static constexpr uint16_t OSR_8192   = 6;
    static constexpr uint16_t OSR_16384  = 7;

    // ---- GAIN register (0x04) ----
    static constexpr uint16_t GAIN_PGAGAIN1(uint8_t g) { return (g & 0x7) << 4; }
    static constexpr uint16_t GAIN_PGAGAIN0(uint8_t g) { return (g & 0x7); }

    // ---- CHn_CFG register (0x09 / 0x0E) ----
    static constexpr uint16_t CH_CFG_MUX_NORMAL = 0;
    static constexpr uint16_t CH_CFG_MUX_AGND   = 1;
    static constexpr uint16_t CH_CFG_MUX_DCVDD  = 2;
    static constexpr uint16_t CH_CFG_MUX_TEMP   = 3;

    // ---- Initialization ----

    void init_pins() {
        gpio_config_t io_conf = {};
        io_conf.intr_type = GPIO_INTR_DISABLE;
        io_conf.mode = GPIO_MODE_OUTPUT;
        io_conf.pin_bit_mask = (1ULL << PIN_CS);
        io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
        io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
        gpio_config(&io_conf);
        gpio_set_level(PIN_CS, 1);

        if constexpr (PIN_DRDY != GPIO_NUM_NC) {
            gpio_config_t drdy = {};
            drdy.intr_type = GPIO_INTR_NEGEDGE;
            drdy.mode = GPIO_MODE_INPUT;
            drdy.pin_bit_mask = (1ULL << PIN_DRDY);
            drdy.pull_down_en = GPIO_PULLDOWN_DISABLE;
            drdy.pull_up_en = GPIO_PULLUP_DISABLE;
            gpio_config(&drdy);
        }
    }

    void init_spi() {
        spi_bus_config_t bus_cfg = {};
        bus_cfg.mosi_io_num = PIN_MOSI;
        bus_cfg.miso_io_num = PIN_MISO;
        bus_cfg.sclk_io_num = PIN_SCK;
        bus_cfg.quadwp_io_num = -1;
        bus_cfg.quadhd_io_num = -1;
        bus_cfg.max_transfer_sz = 32;
        ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus_cfg, SPI_DMA_CH_AUTO));

        spi_device_interface_config_t dev_cfg = {};
        dev_cfg.mode = 1;
        dev_cfg.clock_speed_hz = 1000000;
        dev_cfg.spics_io_num = -1;
        dev_cfg.queue_size = 1;
        ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &dev_cfg, &_spi_dev));
    }

    // ---- SPI Transactions ----

    void read_frame(uint8_t *rx_buf) {
        uint8_t tx_buf[FRAME_BYTES] = {0};
        _transact(tx_buf, rx_buf);
    }

    void send_command(uint16_t cmd) {
        uint8_t tx_buf[FRAME_BYTES] = {0};
        uint8_t rx_buf[FRAME_BYTES] = {0};
        _pack_into(tx_buf, cmd);
        _transact(tx_buf, rx_buf);
    }

    void send_wakeup() {
        send_command(CMD_WAKEUP);
    }

    void send_software_reset() {
        send_command(CMD_RESET);
    }

    void send_standby() {
        send_command(CMD_STANDBY);
    }

    void send_unlock() {
        send_command(CMD_UNLOCK);
    }

    void set_gain(uint8_t gain) {
        uint16_t val = GAIN_PGAGAIN1(gain) | GAIN_PGAGAIN0(gain);
        write_register(REG_GAIN, val);
    }

    // ---- Register Access ----

    void write_register(uint8_t addr, uint16_t val) {
        uint8_t tx_buf[FRAME_BYTES] = {0};
        uint8_t rx_buf[FRAME_BYTES] = {0};
        _pack_into(tx_buf, _opcode_wreg(addr, 0));
        _pack_into(tx_buf + ADS_WORD_SIZE_BYTES, val);
        _transact(tx_buf, rx_buf);
        //ESP_LOGI("ads131", "Wrote reg 0x%02X = 0x%04X", addr, val);
    }

    uint16_t read_register(uint8_t addr) {
        uint8_t tx1[FRAME_BYTES] = {0};
        uint8_t rx1[FRAME_BYTES] = {0};
        _pack_into(tx1, _opcode_rreg(addr, 0));
        _transact(tx1, rx1);

        uint8_t tx2[FRAME_BYTES] = {0};
        uint8_t rx2[FRAME_BYTES] = {0};
        _transact(tx2, rx2);

        return ((uint16_t)rx2[3] << 8) | rx2[4];
    }


    void set_register_bits(uint8_t addr, uint16_t bits_to_set) {
        uint16_t current_val = read_register(addr);
        current_val = current_val | bits_to_set;
        write_register(addr, current_val); // Use 'addr' instead of 'REG_STATUS'
    }

    void clear_register_bits(uint8_t addr, uint16_t bits_to_clear) {
        uint16_t current_val = read_register(addr);
        current_val = current_val & ~bits_to_clear; // Use '~' for bitwise NOT
        write_register(addr, current_val); // Use 'addr' instead of 'REG_STATUS'
    }

    void software_sync() {
        set_register_bits(REG_STATUS, STATUS_F_RESYNC);
    }


    // ---- Utility ----

    static int32_t sign_extend_24(uint32_t val) {
        return (val & 0x800000) ? (int32_t)(val | 0xFF000000) : (int32_t)val;
    }

    static uint32_t extract_status_word(const uint8_t *rx_buf) {
        return ((uint32_t)rx_buf[0] << 16) | ((uint32_t)rx_buf[1] << 8) | rx_buf[2];
    }

    static int32_t extract_channel_data(const uint8_t *rx_buf, int ch) {
        int off = (ch + 1) * ADS_WORD_SIZE_BYTES;
        uint32_t raw = ((uint32_t)rx_buf[off] << 16)
                     | ((uint32_t)rx_buf[off + 1] << 8)
                     | rx_buf[off + 2];
        return sign_extend_24(raw);
    }


    /**
     * @brief Polls the ADC until a fresh conversion frame is ready, parses the data,
     * and returns a signed 32-bit Sample.
     * * @param adc Reference to the Ads131m02 instance.
     * @return Sample The populated sample object containing Ch0 and Ch1 values.
     */
    Sample sample() {
        uint8_t rx_frame[Ads131m02::FRAME_BYTES];
        int polls = 0;

        while (true) {
            read_frame(rx_frame);

            uint32_t status = ((uint32_t)rx_frame[0] << 16) |
                              ((uint32_t)rx_frame[1] << 8)  |
                              rx_frame[2];

            if (status & 0x000300) {
                int32_t ch0_raw = ((int32_t)rx_frame[3] << 16) | ((int32_t)rx_frame[4] << 8) | rx_frame[5];
                int32_t ch1_raw = ((int32_t)rx_frame[6] << 16) | ((int32_t)rx_frame[7] << 8) | rx_frame[8];

                if (ch0_raw & 0x00800000) ch0_raw |= 0xFF000000;
                if (ch1_raw & 0x00800000) ch1_raw |= 0xFF000000;

                return Sample(ch0_raw, ch1_raw, esp_timer_get_time());
            }

            // Yield occasionally to avoid starving other tasks / watchdog
            if (++polls > 200) {
                taskYIELD();
                polls = 0;
            }
        }
    }

private:
    spi_device_handle_t _spi_dev{};

    static constexpr uint16_t BASE_OPCODE_WREG = 0x6000;
    static constexpr uint16_t BASE_OPCODE_RREG = 0xA000;

    static uint16_t _opcode_wreg(uint8_t addr, uint8_t count) {
        return BASE_OPCODE_WREG | ((addr & 0x3F) << 7) | (count & 0x7F);
    }

    static uint16_t _opcode_rreg(uint8_t addr, uint8_t count) {
        return BASE_OPCODE_RREG | ((addr & 0x3F) << 7) | (count & 0x7F);
    }

    static void _pack_into(uint8_t *buf, uint16_t val) {
        buf[0] = (val >> 8) & 0xFF;
        buf[1] = val & 0xFF;
        buf[2] = 0;
    }

    void _transact(const uint8_t *tx_buf, uint8_t *rx_buf) {
        spi_transaction_t t{};
        t.length = FRAME_BYTES * 8;
        t.tx_buffer = tx_buf;
        t.rx_buffer = rx_buf;
        gpio_set_level(PIN_CS, 0);
        ESP_ERROR_CHECK(spi_device_transmit(_spi_dev, &t));
        gpio_set_level(PIN_CS, 1);
    }
};
