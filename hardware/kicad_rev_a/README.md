# Citraverse Rev A — preliminary KiCad interface and placement project

This is an editable KiCad 10 starting project based on the user's circular-board sketch. It is **not a fabrication-ready PCB**: there are no routed traces or implemented regulator/load-switch circuits. The board is now an 80 mm diameter placement to provide clearance for the full-size microSD socket, ESP32 antenna, radar, USB-C, microphone, speaker connector, and factory pads.

Open `citraverse_rev_a_PRELIMINARY.kicad_pro` in KiCad, then open its PCB or schematic. `preview/pcb-placement.png` and `preview/schematic.png` provide views without needing KiCad. The main project contains four copper layers and a 1.6 mm nominal thickness; stack-up and controlled-impedance requirements remain to be agreed with the fabricator.

## Implemented for review

- ESP32-S3-WROOM-1 footprint at the upper edge with antenna overhang and an all-copper-layer keepout reservation. The module pad numbering is sourced from the installed KiCad official ESP32-S3-WROOM-1 symbol. GPIO35–37 are not allocated on the N16R8.
- Centered MRS6240-P2512 footprint derived from the supplied guide's Figure 7-2: 12.00 × 25.00 mm body, 16 plated-through holes in two rows, 1.27 mm pitch, 0.90 × 2.15 mm pads, and 0.65 mm drill. The schematic records the 16 pin names/numbers. Check it against the physical purchased module before ordering any PCB.
- Left microSD socket, proposed Hirose DM3AT-SF-PEJM5 footprint, on its independent SPI bus. The card-detect contacts 9/10 are reserved and not yet used; the shield is `SH`.
- Right HRO TYPE-C-31-M-12 USB-C connector, native USB signal nets and separate 5.1 kΩ CC resistors. Connector sourcing and mechanical fit require confirmation.
- Common six-pin INMP441 breakout-module connector: VDD, GND, L/R, SD, WS, SCK. It retains the 100 nF local VDD bypass, 1 uF bulk bypass, 100 kΩ SD pulldown, and L/R grounded for left-channel operation. Verify the purchased module's printed header order before assembly; inexpensive breakouts occasionally change silkscreen order.
- MAX98357A I2S Class-D amplifier footprint and a two-pin JST-PH speaker connector. The speaker connector is differential (`SPK+`, `SPK-`); neither pin is ground.
- ESP enable pull-up/RC, service boot pull-up, local bypass placeholders and factory recovery connector.
- Four M2.5 mounting-hole candidates. Their placement must be reconciled with the enclosure, acoustic opening and antenna field of view.
- Native schematic connectivity and PCB net names, exported netlist, machine-readable pin contract and a reproducible generation script.

UART nets are explicitly named at the radar-module end: ESP GPIO18 drives `RADAR_RX_AT_MODULE` / radar PB1; ESP GPIO21 receives `RADAR_TX_AT_MODULE` / radar PB0. Radar SPI is reserved on GPIO10/12/11/13, optional lines 9/14; SD SPI is GPIO4/5/7/6; microphone I2S is GPIO15/16/17. GPIO8 is reserved for radar power enable. GPIO47 is only a PA11 reservation; it is not a confirmed data-ready signal.

## Work still required before a working board

1. Check the guide-derived MRS6240-P2512 and INMP441 footprints against physical parts. Confirm SPI role, electrical levels, reset timing, boot requirements and PA11/PA6 behavior with the dev kit/application firmware.
2. Replace `PS1` with a completed, reviewed USB-C power tree: input fuse and TVS, reverse-current protection, a 5 V protected rail for the speaker amplifier, a 3.3 V / 3 A buck for ESP32/SD/mic, and a separately switched 3.3 V radar rail. Prevent back-powering the unpowered radar through its signal pins.
3. Complete the native USB CDC factory-recovery circuit: USB ESD protection, 22 Ω D+/D- series resistors, EN/BOOT reset network, and labelled six-pad factory pogo access for 3V3/GND/EN/BOOT/UART TX/UART RX. A CH340/CP2102 bridge is deliberately not yet placed; native ESP32-S3 USB is the preferred primary factory/OTA path.
4. Complete SD pull-ups, radar series links/decoupling/reset network, USB protection and signal conditioning, status LED and temperature sensing. `STATUS_LED` and `BOARD_NTC` are only reserved MCU nets today.
5. Finalize purchased part numbers; review schematic electrical rules, pin directions and unconnected pins. The current custom block symbols are interface documentation, not a complete electrical schematic. Abstract power/radar pin types cannot validate electrical safety.
6. Keep the 80 mm round PCB, or redesign the SD location before attempting a 70 mm version. Then route the complete board, plan return paths and power planes, verify radio/microphone keepouts and USB geometry, then pass native ERC/DRC and manually review manufacturing outputs. No fabrication files have been generated.
7. Assemble and measure current, transients, heat and data throughput; complete the previously agreed combined-load and fault-injection tests.

## Validation performed

KiCad 10.0.3 successfully loaded and exported the PCB to SVG, and loaded/exported the schematic to SVG and a connectivity netlist. Both previews were visually inspected. The preliminary project has zero routed tracks by design. The KiCad command-line PCB DRC process aborted with exit 134 in this environment and did not produce a DRC report; **no DRC pass is claimed**. The host also emits font-cache warnings during schematic export, but generates the output files.

The generator overwrites these generated project files. After manual KiCad editing, preserve the edited project before re-running it. Run using KiCad's bundled Python, which supplies `pcbnew`:

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 hardware/kicad_rev_a/build_preliminary.py
```

The reference drawing is the user's `IMG_9340.HEIC`. Design context is in the existing project architecture, module-review and ESP32 reliability documents. Their unresolved module/interface assumptions remain unresolved here.
