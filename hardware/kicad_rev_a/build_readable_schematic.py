"""Create a readable electrical-review schematic for the Citraverse Rev A node.

This is intentionally separate from the early placement-study sheet.  It captures
the approved prototype wiring and the required power/control blocks, but it is
not a released manufacturing schematic until the selected power ICs and radar
boot timing have passed electrical review.
"""
from pathlib import Path
import json
import uuid

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "citraverse_rev_a_READABLE.kicad_sch"
uid = lambda: str(uuid.uuid4())
q = lambda value: json.dumps(str(value))

# (reference, value, x, y, [(pin-name, pin-number, direction, net), ...])
parts = [
    ("J1", "USB-C receptacle", 34, 44, [
        ("VBUS", "A4", "power_in", "USB_5V"), ("GND", "A1", "power_in", "GND"),
        ("CC1", "A5", "passive", "USB_CC1"), ("CC2", "B5", "passive", "USB_CC2"),
        ("D+", "A6", "bidirectional", "USB_D+"), ("D-", "A7", "bidirectional", "USB_D-")]),
    ("F1", "PTC fuse 1.5 A hold", 69, 37, [("IN", "1", "passive", "USB_5V"), ("OUT", "2", "passive", "5V_PROTECTED")]),
    ("D1", "5 V TVS diode", 69, 55, [("5V", "1", "passive", "5V_PROTECTED"), ("GND", "2", "passive", "GND")]),
    ("U5", "3.3 V / 3 A synchronous buck", 106, 44, [
        ("VIN", "1", "power_in", "5V_PROTECTED"), ("EN", "2", "input", "3V3_EN"),
        ("GND", "3", "power_in", "GND"), ("VOUT", "4", "power_out", "3V3")]),
    ("Q1", "Radar 3.3 V load switch (>= 1 A)", 151, 44, [
        ("IN", "1", "power_in", "3V3"), ("EN", "2", "input", "RADAR_POWER_EN"),
        ("GND", "3", "power_in", "GND"), ("OUT", "4", "power_out", "RADAR_3V3")]),
    ("R1", "5.1 k CC1", 35, 70, [("CC1", "1", "passive", "USB_CC1"), ("GND", "2", "passive", "GND")]),
    ("R2", "5.1 k CC2", 52, 70, [("CC2", "1", "passive", "USB_CC2"), ("GND", "2", "passive", "GND")]),
    ("C1", "10 uF buck input", 88, 70, [("5V", "1", "passive", "5V_PROTECTED"), ("GND", "2", "passive", "GND")]),
    ("C2", "22 uF buck output", 105, 70, [("3V3", "1", "passive", "3V3"), ("GND", "2", "passive", "GND")]),
    ("C3", "100 nF ESP32 local", 122, 70, [("3V3", "1", "passive", "3V3"), ("GND", "2", "passive", "GND")]),
    ("C4", "100 uF + 100 nF radar local", 151, 70, [("RADAR_3V3", "1", "passive", "RADAR_3V3"), ("GND", "2", "passive", "GND")]),
    ("U1", "ESP32-S3-WROOM-1-N16R8", 105, 125, [
        ("3V3", "1", "power_in", "3V3"), ("GND", "2", "power_in", "GND"), ("EN", "3", "input", "ESP_EN"),
        ("USB_D-", "4", "bidirectional", "USB_D-"), ("USB_D+", "5", "bidirectional", "USB_D+"),
        ("GPIO0 / BOOT", "6", "input", "BOOT_SERVICE"), ("GPIO10 / RADAR_CS", "7", "output", "RADAR_CS"),
        ("GPIO12 / RADAR_CLK", "8", "output", "RADAR_CLK"), ("GPIO11 / RADAR_MOSI", "9", "output", "RADAR_MOSI"),
        ("GPIO13 / RADAR_MISO", "10", "input", "RADAR_MISO"), ("GPIO7 / RADAR_NOTIFY", "11", "input", "RADAR_NOTIFY"),
        ("GPIO9 / RADAR_NRST", "12", "output", "RADAR_NRST"), ("GPIO8 / RADAR_UPD", "13", "output", "RADAR_UPD"),
        ("GPIO18 / RADAR_UART_RX", "14", "input", "RADAR_UART_TX"), ("GPIO17 / RADAR_UART_TX", "15", "output", "RADAR_UART_RX"),
        ("GPIO4 / I2S_WS", "16", "output", "I2S_WS"), ("GPIO5 / I2S_BCLK", "17", "output", "I2S_BCLK"),
        ("GPIO6 / MIC_DOUT", "18", "input", "MIC_DOUT"), ("GPIO21 / SD_CS", "19", "output", "SD_CS"),
        ("GPIO14 / SD_SCLK", "20", "output", "SD_SCLK"), ("GPIO15 / SD_MISO", "21", "input", "SD_MISO"),
        ("GPIO16 / SD_MOSI", "22", "output", "SD_MOSI"), ("GPIO19 / RADAR_POWER_EN", "23", "output", "RADAR_POWER_EN")]),
    ("U2", "MRS6240-P2512 60 GHz radar", 205, 118, [
        ("VCC", "7", "power_in", "RADAR_3V3"), ("VDDIO", "8", "power_in", "RADAR_3V3"),
        ("GND", "6", "power_in", "GND"), ("GND", "15", "power_in", "GND"),
        ("PA0 / CS", "14", "input", "RADAR_CS"), ("PA1 / CLK", "13", "input", "RADAR_CLK"),
        ("PA2 / MOSI", "12", "input", "RADAR_MOSI"), ("PA3 / MISO", "11", "output", "RADAR_MISO"),
        ("PA6 / Notify", "2", "output", "RADAR_NOTIFY"), ("PB0 / UART TX / UPD", "4", "output", "RADAR_UART_TX"),
        ("PB1 / UART RX", "3", "input", "RADAR_UART_RX"), ("NRST", "5", "input", "RADAR_NRST")]),
    ("J2", "microSD socket — SPI3", 190, 170, [
        ("VDD", "4", "power_in", "3V3"), ("VSS", "6", "power_in", "GND"), ("CS", "2", "input", "SD_CS"),
        ("SCLK", "5", "input", "SD_SCLK"), ("MOSI", "3", "input", "SD_MOSI"), ("MISO", "7", "output", "SD_MISO")]),
    ("J3", "INMP441 6-pin microphone module", 43, 170, [
        ("VDD", "1", "power_in", "3V3"), ("GND", "2", "power_in", "GND"), ("L/R", "3", "input", "GND"),
        ("SD", "4", "output", "MIC_DOUT"), ("WS", "5", "input", "I2S_WS"), ("SCK", "6", "input", "I2S_BCLK")]),
    ("C5", "1 uF + 100 nF microphone", 70, 190, [("3V3", "1", "passive", "3V3"), ("GND", "2", "passive", "GND")]),
    ("C6", "10 uF SD local", 165, 190, [("3V3", "1", "passive", "3V3"), ("GND", "2", "passive", "GND")]),
    ("R3", "10 k EN pull-up", 85, 205, [("EN", "1", "passive", "ESP_EN"), ("3V3", "2", "passive", "3V3")]),
    ("C7", "1 uF EN delay", 105, 205, [("EN", "1", "passive", "ESP_EN"), ("GND", "2", "passive", "GND")]),
    ("R4", "10 k BOOT pull-up", 125, 205, [("BOOT", "1", "passive", "BOOT_SERVICE"), ("3V3", "2", "passive", "3V3")]),
    ("R5", "1 k radar UPD isolation", 150, 205, [("UPD", "1", "passive", "RADAR_UPD"), ("PB0", "2", "passive", "RADAR_UART_TX")]),
    ("J4", "Factory pogo: GND / 3V3 / EN / BOOT / TX / RX", 175, 215, [
        ("GND", "1", "passive", "GND"), ("3V3", "2", "passive", "3V3"), ("EN", "3", "passive", "ESP_EN"),
        ("BOOT", "4", "passive", "BOOT_SERVICE"), ("TX", "5", "passive", "FACTORY_UART_TX"), ("RX", "6", "passive", "FACTORY_UART_RX")]),
]

def make_symbol(ref, value, pins):
    half = max(6.35, (max(1, (len(pins) + 1) // 2) + 1) * 2.54)
    pin_defs, pin_places = [], []
    left_count = (len(pins) + 1) // 2
    for index, (name, number, direction, net) in enumerate(pins):
        left = index < left_count
        row = index if left else index - left_count
        x = -17.78 if left else 17.78
        y = (left_count - 1) * 2.54 - row * 2.54
        angle = 0 if left else 180
        pin_defs.append(f'(pin {direction} line (at {x} {y} {angle}) (length 2.54) (name {q(name)} (effects (font (size 1 1)))) (number {q(number)} (effects (font (size .9 .9)))))')
        pin_places.append((net, x, y, left))
    lib = f'(symbol "Citraverse:{ref}" (pin_names (offset .508)) (in_bom yes) (on_board yes) '
    lib += f'(property "Reference" {q(ref)} (at 0 {half + 2.54} 0) (effects (font (size 1.27 1.27)))) '
    lib += f'(property "Value" {q(value)} (at 0 {-half - 2.54} 0) (effects (font (size 1 1)))) '
    lib += f'(symbol "{ref}_0_1" (rectangle (start -15.24 {half}) (end 15.24 {-half}) (stroke (width .254) (type default)) (fill (type background))))'
    pins_text = "".join(pin_defs)
    lib += f'(symbol "{ref}_1_1" {pins_text}) )'
    return lib, pin_places, half

lib_symbols, instances, labels, wires = [], [], [], []
for ref, value, x, y, pins in parts:
    lib, pin_places, half = make_symbol(ref, value, pins)
    lib_symbols.append(lib)
    inst_id = uid()
    instances.append(
        f'(symbol (lib_id "Citraverse:{ref}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{inst_id}") '
        f'(property "Reference" {q(ref)} (at {x} {y-half-2.54} 0) (effects (font (size 1.27 1.27)))) '
        f'(property "Value" {q(value)} (at {x} {y+half+2.54} 0) (effects (font (size 1 1)))) '
        f'(property "Footprint" "" (at {x} {y} 0) (effects (font (size 1 1)) hide)) '
        f'(instances (project "citraverse_rev_a_READABLE" (path "/{inst_id}" (reference {q(ref)}) (unit 1)))))')
    for net, px, py, left in pin_places:
        pin_x, pin_y = x + px, y - py
        end_x = pin_x - 8 if left else pin_x + 8
        wires.append(f'(wire (pts (xy {pin_x} {pin_y}) (xy {end_x} {pin_y})) (stroke (width 0) (type default)) (uuid "{uid()}"))')
        just = 'right' if left else 'left'
        labels.append(f'(label {q(net)} (at {end_x} {pin_y} 0) (effects (font (size 1.1 1.1)) (justify {just} bottom)) (uuid "{uid()}"))')

sections = [
    ("USB-C INPUT + PROTECTION", 18, 22, 78, 78),
    ("3.3 V POWER + RADAR LOAD SWITCH", 80, 22, 168, 78),
    ("ESP32-S3 CONTROLLER", 78, 86, 137, 165),
    ("MRS6240 RADAR — SPI2 + UART CONTROL", 167, 86, 230, 150),
    ("I2S MICROPHONE", 18, 145, 78, 199),
    ("microSD — SPI3", 142, 145, 230, 199),
    ("BOOT / FACTORY SERVICE", 70, 194, 228, 229),
]
section_forms = []
for title, x1, y1, x2, y2 in sections:
    # KiCad's schematic parser accepts text reliably across the KiCad 8/9 formats;
    # avoid decorative primitives here so this remains a portable review sheet.
    section_forms.append(f'(text {q(title)} (at {x1+2} {y1+3} 0) (effects (font (size 1.5 1.5)) (justify left)) (uuid "{uid()}"))')

notes = [
    ("READABLE ELECTRICAL REVIEW — NOT YET A RELEASED FABRICATION SCHEMATIC", 18, 13, 1.8),
    ("Power: 5 V USB-C → fuse + TVS → 3.3 V / 3 A buck. Radar gets a separately switched 3.3 V branch.", 18, 235, 1.15),
    ("Radar: PA0/1/2/3 = CS/CLK/MOSI/MISO; PA6 = Notify; PB0/PB1 = UART; NRST and UPD are controlled only during recovery/programming.", 18, 241, 1.15),
    ("GPIO allocation: radar SPI2 10/12/11/13 + 7/8/9/17/18; mic I2S 4/5/6; SD SPI3 21/14/15/16.", 18, 247, 1.15),
    ("Verify exact regulator/load-switch part values, radar startup timing, ESD layout, and antenna keep-outs before board release.", 18, 253, 1.15),
]
note_forms = [f'(text {q(text)} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid "{uid()}"))' for text, x, y, size in notes]

OUT.write_text(
    f'(kicad_sch (version 20250114) (generator "citraverse_readable_schematic") (uuid "{uid()}") (paper "A3") '
    f'(lib_symbols {"".join(lib_symbols)})' + "".join(instances + wires + labels + section_forms + note_forms) + ')\n'
)
print(OUT)
