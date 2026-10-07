# MRS6240-P2512 Module Review and Integration Plan

**Source reviewed:** `MRS6240-P2512_mmWave_Radar_Module_User_Guide_V1.0-2.pdf`, 17 pages, release date 19 May 2025  
**Module:** Possumic MRS6240-P2512, based on RS6240 60 GHz 2T4R FMCW AiP radar SoC  
**Decision:** suitable as the pilot radar module. Its mechanical footprint is defined from the supplied guide; completion of PCB routing remains blocked on the application firmware and host communication/SDK.

## 1. What this module gives us

- 60 GHz FMCW radar, 2 transmitters and 4 receivers.
- 57–66 GHz operating band, 8 GHz typical sweep bandwidth.
- 120° horizontal and vertical field of view, up to 20 m stated maximum detection range, and stated 1 cm near range (target-dependent).
- On-module antenna array, crystal, flash, radar SoC, CPU, and radar hardware accelerator. The accelerator can perform FFT, CFAR, compression, moving-target detection, and location calculation inside the module.
- 25 × 12 × 1.8 mm plug-in module with 16 through-hole pins and a vendor-recommended footprint.

This is a good match for the camera-free room node: the radar RF and radar signal processing stay on the RS6240, while the ESP32-S3 owns Wi-Fi, audio, SD buffering, device health, cloud transport, and OTA.

## 2. Critical corrections to the previous architecture

### 2.1 Radar supply is 3.3 V, not 5 V

The guide's hardware start-up section explicitly specifies **VCC = 3.3 V and VDDIO = 3.3 V**. Although VCC is specified over 1.7–5.5 V, VDDIO is only 1.7–3.6 V; VCC and VDDIO may be shorted only when the supply does not exceed 3.6 V. For a reliable integrated board, use one controlled 3.3 V radar rail for both pins.

The electrical table lists external supply current up to **800 mA**. Therefore, the old 3.3 V / 1.5 A board budget is not enough as a design guarantee once the ESP32-S3 Wi-Fi peaks, microSD writes, microphone, and margins are included. The revised requirement is a **3.3 V, 2 A minimum peak-rated rail**, with current measurement on the radar branch and a load switch for controlled recovery. The external USB-C adapter remains 5 V / 3 A; it feeds the board regulator and never feeds the radar module directly.

### 2.2 The guide does not document “UART control + SPI data” as the actual application protocol

It says configuration and data acquisition can be implemented through UART, SPI, or I2C, and lists peripheral capabilities. It does not define command IDs, binary radar-frame format, point-cloud schema, baud rate defaults, SPI role, SPI mode, frame rate, timestamping, or a data-ready signal.

That means the earlier split is a sensible **hardware reservation**, but it is not yet an authenticated vendor protocol. Do not start production firmware or freeze exact DMA scheduling based solely on this guide. Obtain the Possumic SDK/demo firmware, host communication protocol, and recommended PC-tool configuration from the supplier/development kit.

### 2.3 No documented data-ready pin

The 16-pin table exposes PA11, PA6, PB1, PB0, NRST, VCC, VDDIO, PA5–PA0, two grounds, and V13. No signal is documented as frame-ready/interrupt. The prior dedicated `DRDY` assumption is therefore removed.

The design should reserve PA11 or PA6 to an ESP32 interrupt-capable GPIO through a zero-ohm link, but leave it uncommitted until vendor firmware confirms whether either is usable as an interrupt/frame-ready output. If no data-ready line is supported, the ESP32 will use the vendor's documented polling/transfer cadence, with SPI DMA and a bounded PSRAM ring.

## 3. Recommended board-level wiring

### 3.1 Power and reset

```text
USB-C 5 V / 3 A adapter
  -> input ESD + fuse + TVS
  -> 3.3 V synchronous buck, >= 2 A peak capacity
  -> switched radar 3.3 V branch -> MRS6240 VCC (pin 7) + VDDIO (pin 8)
  -> ESP32-S3, INMP441, microSD rails

MRS6240 V13 (pin 16) -> no external load; leave as vendor-directed/test-only
MRS6240 NRST (pin 5) -> ESP32 GPIO through a series resistor / reset network
GND (pins 6, 15) -> uninterrupted ground plane and short return paths
```

The radar power switch lets the supervisor power-cycle a stalled module without dropping the audio/SD pipeline. Do not use V13 to power another circuit: the guide calls it an internal 1.3 V supply/output and its wording varies between 1.3 V and 1.5 V.

### 3.2 Host-interface reservation

Use the ESP32-S3's independent SPI2 host for the radar, and SPI3 for the microSD. Connect the full six-pin SPI capability on the radar footprint now, even if the first firmware operates in standard 4-wire SPI:

| MRS6240 pin | Signal | ESP32-S3 role | Rev A recommendation |
|---:|---|---|---|
| 14 | PA0 / SPI0_CS | SPI2 CS | Connect |
| 13 | PA1 / SPI0_CLK | SPI2 SCLK | Connect |
| 12 | PA2 / SPI0_MOSI | SPI2 MOSI | Connect |
| 11 | PA3 / SPI0_MISO | SPI2 MISO | Connect |
| 10 | PA4 / SPI0_HOLD | SPI2 optional data line | Connect through 0 Ω / series footprint |
| 9 | PA5 / SPI0_WP | SPI2 optional data line | Connect through 0 Ω / series footprint |
| 4 | PB0 / UART0_TX | ESP32 UART RX | Connect through series footprint; also supports factory burning |
| 3 | PB1 / UART0_RX | ESP32 UART TX | Connect through series footprint; also supports factory burning |
| 5 | NRST | ESP32 reset GPIO | Connect |
| 1 or 2 | PA11 or PA6 | optional future IRQ/status GPIO | Reserve through 0 Ω link; do not assign a function yet |

The S3 pin assignments on the carrier are still provisional, but must keep radar SPI on SPI2, SD on SPI3, I2S on its own peripheral, and native USB reserved for factory recovery. Use series-resistor footprints on SPI/UART lines. At production reset, ESP32 outputs must be high impedance or at known safe levels so they cannot interfere with the radar's boot or burning mode.

## 4. How to use the module optimally

### Stage A — development kit is the source of truth

1. Use the vendor PC tool/dev kit to enumerate available radar application firmware and modes.
2. Determine whether the module can output raw ADC/range-Doppler/point cloud, tracks, or only processed events; record the exact format, frame rate, bytes/frame, and timestamp behavior.
3. Confirm which transport is used by the tool today. If the tool uses UART for point clouds and SPI only for firmware update, do not force an unproven SPI streaming design.
4. Capture 24 hours of real room data at your intended mounting height/15° angle. Save unmodified host payloads for cloud-team replay.
5. Obtain the vendor's application note for wall mounting, calibration, antenna keep-out, firmware image, host protocol version, and production flashing flow.

### Stage B — choose the production transport from evidence

- **If SPI host streaming is documented and stable:** use radar SPI2 DMA for high-rate frames, retain UART0 for control/diagnostics, and keep the optional PA4/PA5 lines available for quad SPI.
- **If UART is the documented live-data stream:** use UART1 at the vendor-approved baud rate (up to 3 Mbps capability is listed) and leave SPI for firmware update/configuration. This is still completely workable for 24 fps if measured payload throughput fits with margin.
- **If the module's onboard CPU exports tracks/events only:** transmit these losslessly with the radar configuration and firmware version. If cloud ML needs rawer data, negotiate a raw/point-cloud export mode with Possumic rather than reverse-engineering it.

The desired cloud architecture does not change: package whatever vendor-authoritative radar record is produced into ordered one-second batches, write it to SD, and upload only after durable cloud acknowledgement.

## 5. Manufacturing and service implications

- The module can be flashed through UART (PB0/PB1), SPI (PA0–PA3), or I2C (PA4/PA5) using Possumic's BurnTool.
- The guide's burning sequence references PB2, but PB2 is not listed among the 16 exposed pins. Treat that as a documentation discrepancy: do not design a production burning flow around PB2 until Possumic confirms it.
- Put radar UART/SPI/reset pads on the factory pogo fixture. Avoid an exposed consumer connector.
- The module guide's mechanical figure labels the illustrated module P2510 while the document cover identifies P2512. Rev A therefore uses the guide's recommended footprint (12 × 25 mm body, 16 THT pads, 1.27 mm pitch, 0.90 × 2.15 mm pads, 0.65 mm drill); compare it against one physical purchased P2512 module before ordering boards.
- Keep the radar antenna side facing an RF-transparent enclosure window with no copper, ground pour, screw, battery, metal grille, or label directly in its field of view.

## 6. PCB-release checklist

PCB release is blocked until each item is checked off:

1. Possumic provides the host communication protocol and the actual dev-kit firmware/application mode.
2. We confirm live-data interface, SPI role/mode/clock or UART baud, frame size, frame rate, and frame-loss behavior.
3. We measure sustained radar current and define a 3.3 V rail with margin above the 800 mA module maximum.
4. We confirm NRST startup state and whether PA11/PA6 can provide data-ready or health status.
5. We inspect a physical purchased module against the guide-derived Rev A footprint before ordering boards.
6. We run at least a 72-hour combined radar/audio/SD/Wi-Fi soak using the dev kit and then the integrated board.

## 7. Architecture records amended

The following statements in earlier planning documents are superseded:

- “5 V radar rail” is replaced by a switched 3.3 V rail rated for the module's 800 mA maximum input requirement.
- “R6240/R6240 data-ready interrupt” is replaced by a vendor-confirmed transfer cadence; PA11/PA6 remain optional reserved candidates.
- “UART control + SPI data” is now a hypothesis to be proven with the vendor SDK, not a fixed fact.

The wider ESP32-S3 architecture remains valid: separate SPI2 and SPI3 buses, I2S audio, SD-backed lossless queue, cloud-side analytics, health monitoring, and rollback OTA.
