#pragma once

#include <cstdint>

/**
 * @brief Represents a sample from the ADS131M02 ADC.
 */
class Sample {
public:
    /**
     * @brief Constructor for a Sample.
     * @param ch0 The 24-bit value from channel 0.
     * @param ch1 The 24-bit value from channel 1.
     */
    Sample(int32_t ch0, int32_t ch1, int64_t timestamp) : ch0_(ch0), ch1_(ch1), timestamp_(timestamp) {}

    /**
     * @brief Get the value from channel 0.
     * @return The 24-bit value.
     */
    int32_t getCh0() const { return ch0_; }

    /**
     * @brief Get the value from channel 1.
     * @return The 24-bit value.
     */
    int32_t getCh1() const { return ch1_; }

    int64_t getTimestamp() const { return timestamp_; }

private:
    int32_t ch0_;
    int32_t ch1_;
    int64_t timestamp_;
};
