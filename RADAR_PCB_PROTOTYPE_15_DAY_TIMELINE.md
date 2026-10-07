# Radar + PCB Prototype Timeline

**Original target:** complete the integrated radar and PCB prototype within 15 calendar days of receiving the MRS6240 radar module.

## Expedited target — 16 October

This replaces the original 15-day schedule. It is a compressed prototype plan, contingent on same-day decisions, Rush fabrication at Lion Circuits, and Bengaluru collection rather than normal shipping.

| Date | Work | Required output |
| --- | --- | --- |
| 7 Oct | Validate the physical radar, data transport, current, footprint orientation; freeze BOM and 80 mm mechanical placement. | Validated hardware assumptions. |
| 8 Oct | Complete routing, ERC/DRC and DFM; generate Gerbers; place Lion Circuits **Rush** order. | Manufacturing package and portal-confirmed `Ships Before` date. |
| 9–14 Oct | Fabrication; in parallel stage components and validate firmware/test fixtures on development hardware. | Boards and assembly material ready. |
| 14 Oct | Target local collection in Bengaluru and visual inspection. | Bare boards received. |
| 15 Oct | Assembly plus power-first bring-up: USB flashing and regulated rails. | Safe boot pass. |
| 16 Oct | Integrate radar, audio, microSD and Wi-Fi/cloud; demo and issue log. | Pilot prototype demonstration. |

### Non-negotiable gates

1. Do not order after 8 Oct. The physical radar-footprint fit check and ERC/DRC review must complete before that release.
2. Use Lion Circuits Rush instead of the cost-focused Make in India service. Confirm the exact `Ships Before` date before placing the order; advertised times vary by selected specifications.
3. Treat 16 Oct as a prototype demonstration target. It cannot replace the later 72-hour combined-load or two-year reliability validation.

## Planned schedule

| Days | Scope | Exit condition |
| --- | --- | --- |
| 1–3 | Analyse the physical radar module; validate pin orientation, mechanical footprint, power draw, UART/SPI operation and data capture; complete the system solution. | A signed-off interface and mechanical checklist. |
| 4–6 | Complete schematic, PCB placement/routing, ERC/DRC review, manufacturing package and assembly notes. | Fabrication-release package reviewed and approved. |
| 7–10 | PCB fabrication. | Fabricated boards received and visually inspected. |
| 11–15 | Assembly, bring-up, integration and test: power, flashing/OTA, Wi-Fi, radar stream, microphone capture, SD buffering, speaker, and fault recovery. | One stable integrated prototype demonstrated with an issue log. |

## Critical release gate

The Day 4–6 PCB work may not be released to fabrication until the Day 1–3 module validation confirms:

- radar module pin-one orientation and guide-derived footprint against the physical module;
- host transport and live-frame operation through the dev kit;
- 3.3 V radar current under active streaming;
- microSD, USB-C, INMP441 six-pin module, speaker connector and enclosure mechanical clearances.

Any failure at this gate should shift fabrication rather than produce an untestable board.
