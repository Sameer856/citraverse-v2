idf_component_register(SRCS "main.c" "radar_payload.c" "radar_control.c" "radar_wifi.c" "radar_audio.c"
    INCLUDE_DIRS "." PRIV_REQUIRES host_driver esp_timer esp_driver_uart esp_driver_gpio spiffs esp_wifi esp_event esp_netif nvs_flash esp_http_server json
    REQUIRES esp_driver_i2s
    EMBED_TXTFILES "viewer.html" "fall.js" "audio.html")
if(NOT DEFINED RADAR_IMAGE)
    set(RADAR_IMAGE "$ENV{RADAR_IMAGE}" CACHE FILEPATH "Vendor P2512 radar image")
endif()
if(NOT EXISTS "${RADAR_IMAGE}")
    message(FATAL_ERROR "Set RADAR_IMAGE to radar_analysis_mrs6240_p2512.img from the vendor SDK")
endif()
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/radar_image_files")
configure_file("${RADAR_IMAGE}" "${CMAKE_BINARY_DIR}/radar_image_files/radar.img" COPYONLY)
spiffs_create_partition_image(radar_image "${CMAKE_BINARY_DIR}/radar_image_files" FLASH_IN_PROJECT)
