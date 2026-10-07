# ESP32-S3 I/O, 24×7 Reliability, and Cloud Transport Decision

**Status:** ESP32-S3 dual-SPI decision verified; MRS6240 transport/pin functions remain provisional until Possumic SDK/protocol is received  
**Date:** 4 October 2026  
**Target hardware:** ESP32-S3-WROOM-1-N16R8 class module, 16 MB flash / 8 MB in-package octal PSRAM

## Executive conclusion

The ESP32-S3 is suitable for this five-unit pilot and has enough independent hardware to run the R6240, microSD, I2S microphone, Wi-Fi, health logic, and OTA continuously. It has **two general-purpose SPI controllers** (`SPI2` and `SPI3`), both DMA-capable, in addition to SPI controllers used internally for flash/PSRAM. The correct topology is therefore:

```text
MRS6240 UART/SPI          -> reserve both; vendor SDK selects live-data/control transport
MRS6240 SPI option        -> SPI2 + DMA, with optional PA11/PA6 status reservation
microSD queue            -> SPI3 + DMA
INMP441 audio            -> I2S0 + DMA
USB factory service      -> native USB on GPIO19/GPIO20
```

The radar and SD card must not share a bus. The ESP32-S3 is not the main two-year lifetime risk; the bigger risks are microSD endurance, power quality, USB cable/adapter quality, enclosure temperature/humidity, and firmware defects that create a false-healthy state.

## 1. What has been verified

The official ESP32-S3 datasheet specifies two general-purpose SPI ports, two I2S interfaces, three UARTs, a general DMA controller with five TX and five RX channels, and 45 programmable GPIOs. `SPI2` and `SPI3` are both general-purpose controllers with DMA support. SPI signals can be mapped through the GPIO matrix; at 40 MHz or lower, Espressif documents no performance difference versus IO_MUX routing.

This means the earlier architecture is technically feasible. The S3 is not trying to time-share one SPI peripheral between radar and SD; it has two independent application SPI hosts. Flash and 8 MB octal PSRAM are internal to the N16R8 module and are not available as external application buses.

Sources: [ESP32-S3 Series Datasheet](https://documentation.espressif.com/esp32_s3_datasheet_en.pdf), [ESP-IDF SPI Master Guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/spi_master.html), [ESP32-S3 Hardware Design Guidelines](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/).

## 2. Provisional pin budget

The MRS6240 electrical guide states that UART, SPI, and I2C can support configuration/data acquisition but does not define its host protocol. This allocation reserves standard and quad SPI, UART0, reset, and a future status signal so the production transport can follow the vendor SDK without a PCB respin.

| Function | Peripheral | Proposed GPIOs | Notes |
|---|---|---|---|
| MRS6240 UART0 TX/RX | UART1 | GPIO18 / GPIO21 | Reserve for vendor control/live data and factory burning |
| MRS6240 SPI CS/CLK/MISO/MOSI | SPI2 | GPIO10 / GPIO12 / GPIO13 / GPIO11 | MRS6240 PA0–PA3; connect all |
| MRS6240 optional quad data | SPI2 | GPIO9 / GPIO14 | MRS6240 PA5/PA4; reserve until protocol confirms need |
| MRS6240 optional status | GPIO interrupt | GPIO47 | Reserve for PA11 or PA6; no DRDY is documented |
| MRS6240 reset | GPIO output | GPIO48 | Connect to NRST for controlled recovery |
| microSD CS/CLK/MISO/MOSI | SPI3 | GPIO4 / GPIO5 / GPIO6 / GPIO7 | Separate SPI host, lower-priority storage traffic |
| INMP441 BCLK/WS/DOUT | I2S0 | GPIO15 / GPIO16 / GPIO17 | Dedicated I2S/DMA capture |
| Factory USB D-/D+ | USB | GPIO19 / GPIO20 | Keep reserved for programming/debug and field recovery |
| RGB status LED | GPIO | GPIO38 | Low-current external LED/light pipe |
| Spare/test signals | GPIO | GPIO1, GPIO2, GPIO8, GPIO39–GPIO42 | Keep at least two unused on Rev A |

This uses 18 active external signals, or 20 if the R6240 uses quad SPI. It leaves reserve capacity on a WROOM-1 module. Do **not** allocate GPIO0, GPIO3, GPIO45, or GPIO46 to external peripherals that can affect their boot strapping state. On the N16R8 variant, GPIO33–GPIO37 are occupied by the in-package octal PSRAM and are unavailable for this board design.

### Pinout decision gates

1. Obtain Possumic's exact host protocol: chosen UART/SPI/I2C interface, SPI role/CPOL/CPHA/clock if SPI is used, frame boundary, and any usable PA11/PA6 status behavior.
2. If it is standard 4-wire SPI at up to 40 MHz, use the allocation above unchanged.
3. If it is quad SPI, connect GPIO9/GPIO14 to the reserved radar data lines and keep SPI2 dedicated.
4. If it requires a clock above 40 MHz, preserve the SPI2 IO_MUX mapping and use short controlled traces. SD remains on SPI3 through the GPIO matrix at a conservative validated speed.
5. Run the final pin map through Espressif's schematic checklist and generate a real PCB netlist review before fabrication. This is the schematic-freeze gate, not an afterthought.

## 3. Keeping capture seamless under 24×7 load

### Hardware isolation

- MRS6240 SPI2 has independent DMA transactions if SPI is selected; a status/interrupt line is used only if Possumic documents it.
- microSD SPI3 uses independent DMA and is the only filesystem bus.
- I2S0 has its own DMA receive buffers.
- USB is factory-only; it does not compete with runtime sensor paths.
- The R6240 gets a separately switchable supply/reset path so the MCU can recover the radar without restarting audio capture.

### Firmware scheduling

1. `radar_spi_rx` is the highest-priority task. Its only job is to take a validated raw frame and place it in a fixed PSRAM ring.
2. `audio_i2s_rx` is high priority and drains I2S DMA into a separate fixed ring.
3. `spool_writer` has lower priority and writes one-second radar batches plus 30-second WAV files to SPI3.
4. `uploader` is lowest priority. It copies a finalized file from SD into PSRAM, releases all SD ownership, then uses Wi-Fi/TLS.
5. Every ring has high-water and overflow counters. An overflow is a fault, never an ignored statistic.

Use a five-second radar PSRAM buffer **at the measured maximum frame size**, not an assumed frame size. The acceptance test must run R6240 full rate, 16 kHz audio, active SD writes, and deliberately slow Wi-Fi uploads for at least 72 hours. Success means zero radar-frame and audio-byte drops.

## 4. Two-year lifetime: what can and cannot be calculated now

Two years of uninterrupted operation is **17,520 hours per device**. Five pilot devices yield only 87,600 device-hours, so the pilot cannot statistically prove a two-year failure rate. For example, observing zero critical failures in 87,600 hours gives only a loose 95% upper bound of roughly 3 failures / 87,600 hours, not a meaningful component FIT prediction.

We should therefore state a product target, not invent a chip failure rate:

```text
Pilot target: ≥95% of deployed devices complete two years without a hardware replacement,
excluding external site power/network outages and physical damage.
```

The target is made credible by component qualification, design margin, accelerated testing, and field health data—not by a paper calculation from the ESP32-S3 alone.

### Reliability plan

| Risk | Design response | Qualification evidence before deployment |
|---|---|---|
| ESP32-S3/module | Buy traceable Espressif modules from one approved source; no counterfeit bare modules | Incoming inspection and 72-hour full-load soak per assembled unit |
| Heat | Four-layer PCB, ground plane, no heat source under antenna, thermally derated 3.3 V regulator | 72-hour full-load enclosure soak at 45°C ambient; module/board temperature stays at least 15°C below the chosen module's rated maximum |
| 3.3 V brownouts | 5 V/3 A approved adapter, 3.3 V synchronous buck rated ≥2 A peak, switched radar branch rated for its specified 800 mA demand, 10 µF + local 0.1 µF decoupling, supervisor/brownout detector | 20 controlled power interruptions plus low-voltage ramp test under Wi-Fi transmit, radar activity, and SD write |
| USB cable/UPS port | Strain relief, replaceable certified adapter/cable, TVS/eFuse, installer voltage/load check | Cable pull/bend and 24-hour loaded-adapter test |
| microSD wear | Genuine high-endurance/industrial 64 GB card with published endurance comfortably above the projected write load | Sustained write/read verification using the exact pilot card SKU; reject any counterfeit/slow cards |
| Audio write load | Audio alone is about 2.02 TB over two years before filesystem overhead | Include this figure in SD-card endurance selection, not just capacity selection |
| Humidity/dust | ABS/ASA enclosure, protected microphone mesh, conformal coat only where it does not affect RF/mic/radar | Two-week real-site environmental node plus visual inspection |
| Firmware/heap leak | ESP-IDF, fixed buffers, task heartbeats, watchdogs, core/reset logs, A/B OTA rollback | 72-hour soak plus injected Wi-Fi/SD/radar faults; zero unexplained resets or drops |

Espressif's design guidance recommends a four-layer PCB, input decoupling/ESD protection, and a power source with at least 500 mA available to the S3 itself. This design exceeds that minimum because Wi-Fi bursts, external peripherals, and board margin are material. The regulator must be validated thermally with the real radar and SD card, not selected by nominal MCU current alone. [Espressif schematic checklist](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html) and [four-layer layout guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html).

## 5. Heat-control approach

The S3 is not performing cloud AI; it is doing DMA capture, storage, networking, and transport. That is an appropriate workload, but Wi-Fi uploads and a sealed 3D-printed enclosure can still make heat a system concern.

- Choose a module variant whose published ambient-temperature rating covers the site envelope; do not treat a consumer dev-board rating as the product rating.
- Put the 3.3 V buck, radar power switch, and SD socket away from the S3 antenna keep-out and away from the radar antenna window.
- Use a four-layer board with a continuous ground plane and thermal vias under heat-producing components. Do not use the ESP module antenna end as a heatsink or cover it with enclosure metal.
- Place an NTC near the regulator/S3 region. Report board temperature; use it for health alarms and adaptive upload throttling, never to stop capture silently.
- Keep Wi-Fi power-save policy configurable. Mains-powered pilots may disable it when needed for predictable uploads, but measure temperature/current before treating that as the default.
- Set a thermal validation criterion from the **chosen module's** official maximum ambient rating. Do not hard-code a threshold until the exact module SKU is approved.

## 6. Alternatives to direct device → GCS bucket

| Option | Best use | Strengths | Costs / weaknesses | Recommendation |
|---|---|---|---|---|
| Direct GCS resumable upload | Archive-only proof of concept | Few cloud components; current audio code already works | Long-lived device credential exposure; weak real-time control/health contract; raw bucket is not a message system | Keep only as temporary audio fallback |
| Device → Cloud Run ingest → GCS + Pub/Sub | Five-unit direct-to-cloud pilot | Simple device API, per-device auth, durable ACK, real-time processing, OTA/health endpoint | Must run an always-warm service and implement streaming body handling correctly | **Recommended pilot default** |
| Device → managed MQTT broker → bridge to Pub/Sub/GCS | Larger future fleet / continuous telemetry | QoS 1, persistent sessions, topic model, command channel | Broker cost, certificate/device provisioning, another operational system | Strong scale path after pilot |
| Device → per-site Pi/N100 gateway → cloud | Dementia centre / weak internet sites | Local buffering, one cloud identity, simplified nodes, local diagnostics/OTA; survives internet outage | Extra device, site maintenance, added deployment cost | Recommended Phase 2 for care facilities; not needed in homes initially |
| Device → Pub/Sub HTTP directly | Not recommended for ESP32 | Removes custom ingress service | OAuth/service-account flow is unsuitable for constrained field nodes | Do not use |

## 7. Architecture change alerts

The following conditions should trigger an architecture review before fabrication:

1. MRS6240 live-data rate exceeds the UART/SPI/PSRAM/SD write budget measured at full output.
2. MRS6240 vendor protocol requires a host transport or GPIO behavior not supported by the reserved UART/SPI/reset/PA11/PA6 plan.
3. Actual 72-hour combined-load testing reports any radar/audio drops, watchdog resets, or thermal margin failure.
4. Two-hour outage recovery cannot drain backlog before the next expected outage window.
5. The selected microSD card's published endurance is below the two-year audio-write requirement plus safety margin.
6. The cloud ingest service buffers whole audio objects or cannot issue idempotent durable acknowledgements.

Any one of these is not a minor bug; it means we pause PCB release and revise the design.
