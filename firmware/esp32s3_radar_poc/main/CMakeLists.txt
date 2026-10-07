idf_component_register(SRCS "main.c" "radar_payload.c" "radar_control.c"
    INCLUDE_DIRS "." PRIV_REQUIRES host_driver esp_timer esp_driver_uart esp_driver_gpio)
