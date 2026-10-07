# Protocol notes — evidence scope

Sources are local vendor HIF Reference V1.2 text, HostSample V1.0.1, SDK V2.1.2, and RadarAnalysisTool V1.2.0.13 Pose script; see hashes in `source_manifest.json`. These sources describe firmware families; compatibility with the live image is only proven for the recorded queries and captured point stream.

## UART control

Observed COM6 uses 115200 8N1, no flow control, ASCII command + one `0D` (CR). Replies include command echo, CR/LF, a NUL, `Command Success`, and `psic:/$` prompt. Serialize commands; record bytes and wait for success or a bounded timeout. Stop the sequence on errors. `query_control.py` executes only the seven read-only commands in the successful JSON log.

Vendor-script / existing-host candidate configuration below is **not executed or validated in this session**:

```text
mmwc stop
mmwc comtype 0
mmwc baudrate 1000000
mmwc hif_retry 0
mmwc mode 4 2
mmwc mode get
mmwc freq 58000
mmwc range 10240 40
mmwc veloc 960 60
mmwc chirp_num 1
mmwc frame 50 0
mmwc clutter_rm 0
mmwc dop_fft 1
mmwc coord cart
mmwc cfar 1 17 0
mmwc mpoint 1
mmwc micro_frame 4
mmwc report points 0
mmwc dop_fft get
mmwc start
```

Check mode and Doppler readback before start. Do not blindly replay against another application image. In the supplied shell source, `baudrate` and `comtype` parse their argument with `atoi`; `get` is NOT a safe query for those commands. `dop_fft` also uses numeric parsing: use `1`, not `on`. Prior workspace notes report an older image rejecting an `intv` write; no interval setter was tested here. The Pose Lua specifies 2T4R, 2DFFT, 58 GHz, 50 ms and Cartesian output; it is not evidence of current-draw or timing performance.

## SPI and Notify (documented, not measured)

HIF reference section 2.2: radar is slave, host supplies SPI clock. PA0 CS, PA1 CLK, PA2 MOSI, PA3 MISO; default Notify is PA6 output. ESP32 sample `hal_com_spi.c` sets mode 0 (CPOL=0, CPHA=0), no flags, and default 8000000 Hz. The driver's software upper clamp is not a validated radar clock limit. The HIF manual advises extra layout care above 5 MHz. The ESP32 sample README initially describes AS2525 but later explicitly gives a P2512 Tracking example; validate the exact firmware combination.

HIF section 3.2.3 passive reporting: Notify rises -> host sends POLL -> device lowers Notify while preparing data -> Notify rises -> host reads HIF data and checks More/Notify -> continue or finish. Notify indicates transport readiness, not a guaranteed one-to-one frame-ready strobe. Active UART reporting sends data without this polling handshake.

HIF section 3.2.1 SPI wake-up: send `55 FF 55 FF`, wait 1 ms, read four bytes for `79 79 79 79`; on mismatch wait 10 ms and retry with a host-imposed timeout. Wake-up is distinct from cold boot or reset. HIF section 5.1.2.2 documents NRST low disabling operation and high enabling it; pulse width, power sequencing and startup latency remain unmeasured.

## Wire payload

HIF base header is 6 bytes: magic A5; Check8; four-byte little-endian MsgHeader. Sum of all six bytes modulo 256 must be FF. Byte 2 encodes direction/type (bits 0–1), request (2), encryption (3), Check32 present (4), More (5), extension (6), alternate checksum (7). Byte 3 is MsgID. Bytes 4 and low nibble of 5 contain the 12-bit payload byte count. Byte 5 bits 4–6 are sequence and bit 7 is fragmentation. Optional trailing Check32 is complement of the sum of little-endian DWORDs over bytes 2–5 plus payload, zero-padded for calculation only. It is not CRC32.

C3 point upload begins with three little-endian uint32 values: frame index, total frame length in DWORDs, and chunk offset in DWORDs. Reassemble uploads before interpreting TL blocks; HIF message fragmentation is a separate byte-offset layer and is not supported by the small examples. Never confuse bytes and DWORDs.

Reassembled point block: uint8 type=4, uint8 flags, uint16 payload length in bytes, followed by 12-byte points. Flag bit 0 means Cartesian, bit 1 means presence (micro-motion). Flags 1/3 use signed int16 X/Y/Z and velocity, unsigned uint16 SNR and reserved. XYZ use centimetres, velocity cm/s, SNR hundredths of dB. Polar flags 0/2 need separate range/angle handling. Type 5 tracks and ADC/cube payloads are not point blocks. The SDK contains differing cube-header layouts; bind any cube decoder to the exact application before using it.

## Saved raw capture format

`uart_capture.bin` is a flat concatenation of bytes read from COM5, with no added lengths or headers, no .NET deserialization and no byte removal. It may begin/end inside a packet. This is raw UART transport data carrying processed points, NOT raw ADC.

Each `uart_chunks.jsonl` record is `{elapsed_s, offset, length}`: host monotonic seconds since capture start, byte offset into the bin, and read length. USB reads do not define packet boundaries. `frame_arrivals.jsonl` records `{elapsed_s, frame, points}` when the original decoder completed a frame; timestamps are not sensor acquisition times. UTC start, serial settings, duration and raw SHA-256 are in `capture_summary.json`.

For future captures retain firmware/image hash, board identity, switch/wiring state, exact configuration transcript, supply/instrument settings and error counters alongside the same raw evidence. Native vendor .dat exports may be serialized containers; do not label them UART byte streams or use unsafe object deserialization.

## Live SPI follow-up correction

On V5.3.1.0, explicit `mmwc comtype 1` followed by `mmwc report points 0` and `mmwc start` produced SPI point callbacks. `mmwc stop` disables point reporting in the SDK; reissue the report command before restarting. A 41 ms requested period produced 734 consecutive frames in a 30-second capture. Source-default 8 MHz and the vendor DLL selector-3 setting of 7.5 MHz are different host configurations; neither is an electrical measurement in this record.

The vendor callback `payloadData` starts at the reassembled TL point blocks, without the 12-byte C3 upload header or HIF framing. `frameLen` in these captures equals payload bytes divided by four. Do not feed these payloads to the UART HIF stream parser or infer SPI transaction size from callback length. Use `analyze_vendor_spi.py` for these files. Base64 preserves callback bytes exactly, but transport bytes have already been stripped by the DLL.
