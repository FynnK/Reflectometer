idf_component_register(
    SRCS "main.cpp"
    INCLUDE_DIRS "."
    REQUIRES driver
    PRIV_REQUIRES esp_driver_spi esp_driver_gpio esp_driver_ledc esp_timer
)