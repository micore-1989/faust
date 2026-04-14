# faust — Complete Parts List

**Project:** AI-native pentesting handheld
**Status:** All hardware purchasing complete
**Order date:** April 13, 2026
**Build window:** April 14 – May 15, 2026
**Total spend:** ~$2,059 (under $2,250 working budget by ~$191)

---

## Order Summary

| # | Vendor | Order method | Subtotal | Status | Expected arrival |
|---|--------|--------------|----------|--------|------------------|
| 1 | AliExpress | Multi-seller cart | ~$142 | Placed | ~Apr 25 – May 5 |
| 2 | Hacker Warehouse | Direct | $508 | Placed (HackRF Pro **backorder**) | ~Apr 27 – May 11 |
| 3 | Adafruit | Direct | ~$617 | Placed | ~Apr 16-18 |
| 4 | Electronic Cats | Direct | ~$38 | Placed | ~Apr 18-22 |
| 5 | 18650BatteryStore | Direct | ~$63 | Placed | ~Apr 20-25 (DOT ground) |
| 6 | Geekworm | Direct | ~$75 | Placed (HK ship) | ~Apr 22-28 |
| 7 | Waveshare | Direct + DHL Express | ~$100 | Placed | ~Apr 17-20 |
| 8 | Amazon | Prime | ~$475 | Placed (ICE Tower→Armor Lite V5 swap done) | ~Apr 14-15 |
| 9 | Pololu | Direct | ~$41 | Placed | ~Apr 16-18 |

---

## Vendor 1: AliExpress (~$142)

Small parts and sensors. Multi-seller cart, shipping is staggered and slow (2-3 weeks).

| Item | Spec / Model | Qty | Price | Description & Use |
|------|--------------|-----|-------|---------------------|
| Nano SIM tray | Micro Nano SIM Card Push-Push 6P 1.4H | 5 | $2.26 | Surface-mount SIM card slot. Pre-wired into Faust shell to enable cellular modem add-on for MK2 without redesign. Five-pack provides spares. |
| Hookup wire kit | UL1007 22AWG, 5 colors × 10m | 1 | $9.23 | Solid-core insulated wire for all internal point-to-point wiring. 22AWG handles ~3A safely. |
| JST/Dupont connector kit | 460pc Micro JST-XH + Dupont 2.54mm, 2-6 pin | 1 | $7.77 | Crimp connectors for module interconnects. JST-XH for power+data; Dupont for signal lines. |
| T5577/EM4305 blank cards | 125 kHz programmable RFID, 5-pack | 1 | $4.96 | Blank LF RFID cards for the "Clone access credential" Pursuit. |
| RDM6300 reader module | 125 kHz LF UART read-only | 1 | $3.18 | Backup LF RFID reader. Simple UART interface for fast bring-up. |
| Heavy-duty toggle switch | 12V 5-pack with waterproof cover | 1 | $6.02 | Physical RF kill switch on Faust. Cuts power to all radio peripherals while leaving Faust↔Mephisto link intact. |
| WH148 potentiometer kit | B5K/10K/20K/50K/100K linear taper | 1 | $5.56 | The B10K is used for analog backlight brightness control. Other values are spares. "B" prefix = linear taper. |
| IRLZ44N MOSFETs | TO-220, logic-level | 10 | $2.84 | Logic-level N-channel MOSFETs for switching LEDs (PWM) and high-current rails from 3.3V GPIO. |
| INA219 breakout | 2-pack, bi-directional current sensor | 1 | $2.93 | I2C current and voltage sensor. Battery monitoring and Pi power draw measurement. |
| NEO-M9N GPS module | u-blox GY-NEO-M9N with antenna | 1 | $24.18 | Multi-constellation GNSS receiver (GPS, GLONASS, Galileo, BeiDou). Used for the Wardrive Pursuit. |
| DS18B20 temperature probes | Waterproof thread, 1m lead, 5-pack | 1 | $7.60 | 1-Wire digital temperature sensors. Three are used in faust (Pi/Hailo/battery temps). |
| IR TX/RX module | IR LED + TSOP38238 receiver, 5-set | 1 | $5.30 | Infrared transmitter and 38 kHz receiver pair for capturing/replaying IR remote codes. |
| CC1101 + SMA antenna | 315/433/868/915 MHz sub-GHz | 1 | $4.21 | Sub-GHz transceiver. Backup to HackRF Pro for sub-GHz keyfob/garage-door work. SPI interface. |
| SS22F25-G7 slide switch | DPDT 2P2T panel-mount | 1 | $3.40 | Master power switch for Faust. DPDT used in DPST configuration. |
| SMA Female bulkhead adapter | Zigotronic waterproof panel mount | 6 | $16.80 | Bulkhead-mount SMA Female connectors for routing antenna connections through Faust's shell. |
| T5577/EM4305 reader/writer | Combined 125 kHz LF RFID with antenna | 1 | $5.88 | Combined LF RFID read+write module. Primary tool for cloning HID Prox, EM4100, T5577 cards. |
| u.fl/IPEX to SMA pigtail | 10cm, SMA-K (female) ends, 5-pack | 1 | $1.54 | Internal antenna routing cables. Connects board-mount u.fl connectors to SMA bulkheads on shell. |
| Tactile pushbuttons | 6×6×4.3mm 4-pin, 20-pack | 1 | $1.37 | Physical UI buttons. Six are used in Faust. |
| DS9092 iButton probe | TM1990 probe + 5 blank iButton keys | 1 | $16.57 | Maxim/Dallas iButton (1-Wire) reader probe with 5 blank keys for cloning. |
| PN532 NFC module | v3 13.56 MHz RFID, US-ship | 1 | $10.65 | High-frequency NFC/RFID transceiver. Reads/writes/emulates MIFARE Classic, NTAG, ISO 14443 A/B. |

**Subtotal: ~$142**

---

## Vendor 2: Hacker Warehouse ($508)

Software-defined radio and antennas. **HackRF Pro is on backorder** — single longest-lead item in the build.

| Item | Spec / Model | Qty | Price | Description & Use |
|------|--------------|-----|-------|---------------------|
| **HackRF Pro** | Great Scott Gadgets, USB-C, 100 kHz – 6 GHz, TCXO, DC-spike-free | 1 | $400 | Primary software-defined radio. Half-duplex transceiver, 100 kHz-6 GHz, up to 20 Msps. Replaces the discontinued HackRF One. Backward-compatible with all HackRF One software. USB-C connector. |
| 75~1000 MHz antenna | Telescopic, SMA-Male | 1 | $30 | Equivalent to ANT500. Sub-GHz work (FM radio, garage remotes, keyfobs at 315/433/868/915 MHz). |
| 300~1100 MHz antenna | Telescopic, SMA-Male | 1 | $25 | Equivalent to ANT700. Extends coverage into 1 GHz region. |
| 700~5800 MHz antenna | SMA-Male | 1 | $45 | High-band antenna covering WiFi 2.4 GHz, 5 GHz, LTE bands, Bluetooth. Critical for HackRF-based WiFi/BLE protocol analysis. |
| Shipping insurance | | 1 | $8 | Insurance on $500 backorder item. |
| Discrete packaging | "No HW Labels on Shipment" | — | $0 | Removes Hacker Warehouse branding from shipping label. |

**Subtotal: $508**

---

## Vendor 3: Adafruit (~$617)

Compute, audio, cables. Largest single order.

| Item | PID | Qty | Unit | Total | Description & Use |
|------|-----|-----|------|-------|---------------------|
| Raspberry Pi 5 — 16 GB RAM | 6125 | 1 | $219.50 | $219.50 | Mephisto's primary SBC. 16GB RAM gives substantial headroom for Hailo runtime + agent + OS overhead. |
| Raspberry Pi 5 — 1 GB RAM | 6447 | 2 | $49.50 | $99.00 | Faust's primary SBC + 1 cold spare. 1GB sufficient since Faust runs UI+agent loop+skill dispatch (LLM lives on Mephisto). |
| Raspberry Pi AI HAT+ 2 (Hailo-10H, 40 TOPS) | 6451 | 1 | $200.00 | $200.00 | Mephisto's NPU. 40 TOPS INT4 inference performance, 8GB on-board LPDDR4X RAM. Supports Qwen 2.5-VL 3B (planned model). |
| Raspberry Pi Camera Module 3 — Standard | 5657 | 1 | $29.25 | $29.25 | Rear-facing camera on Faust for VLM work. 12MP autofocus, 75° FoV, IMX708 sensor. |
| Adafruit I2S 3W Class D Amplifier (MAX98357A) | 3006 | 1 | $5.95 | $5.95 | Audio amplifier with built-in I2S DAC. Drives the speaker for UI sounds and TTS. |
| Mini Oval Speaker, 8Ω 1W | 3923 | 1 | $1.95 | $1.95 | Compact speaker element paired with MAX98357A. |
| Official Pi 27W USB-C PD PSU (5.1V 5A) | 5814 | 2 | $14.04 | $28.08 | Wall chargers for Faust + Mephisto. 5A rating mandatory for Pi 5 under sustained load. |
| Pi 5 FPC Display Cable 22-pin↔15-pin, 200mm | 5821 | 1 | $2.70 | $2.70 | DSI display ribbon cable. Pi 5 is 22-pin; Waveshare 8" is 15-pin. |
| Slim Right Angle USB-C to USB-C Cable, 100mm | 6370 | 2 | $6.95 | $13.90 | Captive interconnect between Faust and Mephisto. Right-angle exit keeps cable flat against the dock channel. |
| Panel Mount USB Cable — A Male to A Female | 908 | 1 | $3.95 | $3.95 | External USB-A port on Faust shell for connecting USB devices without opening the device. |
| USB to TTL Serial Cable (CP2102, 3.3V) | 954 | 1 | $9.95 | $9.95 | Serial console cable for headless Pi access during firmware development. |
| USB Type C Breakout — Sunken variant | 6050 | 1 | $2.95 | $2.95 | External USB-C charging port on Faust shell. Sunken variant sits flush in panel cutout. |
| PCB Coaster with Gold Adafruit Logo | 5719 | 1 | FREE | — | Adafruit's free promo gift. |

**Subtotal: ~$617** + Adafruit shipping

---

## Vendor 4: Electronic Cats (~$38)

WiFi/BLE recon module. Substituted for sold-out JustCallMeKoko board.

| Item | Qty | Price | Description & Use |
|------|-----|-------|---------------------|
| ESP32-S3 Marauder Add-On | 1 | ~$35 | ESP32-S3 board pre-flashed with ESP32 Marauder firmware. Handles all WiFi (deauth, handshake capture, PMKID, Evil Portal) and BLE (scan, spam) skills. Connects to Faust over USB-serial. Onboard microSD slot for PCAP capture; 3D-printed enclosure included. |
| Shipping | — | ~$3 | |

**Subtotal: ~$38**

---

## Vendor 5: 18650BatteryStore (~$63)

18650 lithium cells. Critical to source from a reputable vendor — Amazon's 18650 market has ~30% counterfeit rate.

| Item | Spec | Qty | Price | Description & Use |
|------|------|-----|-------|---------------------|
| Molicel P30B 18650 | 3000mAh, 30A continuous, flat top, INR | 10 | $5.50 = $55.00 | Lithium-ion cells: 4 in Faust X1202 UPS + 2 in Mephisto X1201 UPS + 4 spares. P30B substituted for spec'd P28A: +200mAh capacity, -5A discharge — net better for low-draw application. Flat-top required for spring-loaded UPS HAT sleds. |
| Shipping (DOT ground) | | | ~$8 | Lithium cells must ship ground per DOT regulations. |

**Subtotal: ~$63**

---

## Vendor 6: Geekworm (~$75)

UPS HATs that convert 18650 cells into Pi-compatible 5.1V/5A regulated power with battery backup.

| Item | Qty | Price | Description & Use |
|------|-----|-------|---------------------|
| Geekworm X1202 4-cell 18650 UPS HAT for Pi 5 | 1 | ~$38 | Faust's power management board. 4S battery (~14.8V nominal) regulated to 5.1V/5A output. USB-C PD input for wall charging. ~4-6 hours runtime at typical load. |
| Geekworm X1201 2-cell 18650 UPS HAT for Pi 5 | 1 | ~$28 | Mephisto's power management. 2S (~7.4V) → 5.1V/5A. ~3-4 hours active inference / ~8 hours standby. |
| Shipping (Hong Kong) | | ~$10 | |

**Subtotal: ~$75**

---

## Vendor 7: Waveshare (~$100)

Faust's main display. Critical hardware revision check completed (Rev 2.2+ Pi 5 safe).

| Item | Spec | Qty | Price | Description & Use |
|------|------|-----|-------|---------------------|
| 8inch DSI LCD (C) — SKU 23448 | 1280×800 IPS, 5-point capacitive touch, DSI, **Rev 2.2** | 1 | $74.99 | Faust's main display. Rev 2.2 fixes Rev 2.1 short-detection bug that bricks Pi 5 DSI ports (confirmed via Waveshare support before order). |
| DHL Express shipping | | | ~$25 | Cuts standard 7-14 day shipping to 3-5 days. |

**Kit includes:** Display panel, 12cm DSI cable (22-pin Pi 5 compatible), 50mm + 160mm 15-pin FPC cables, PH2.0 4-pin power/I2C cable, screws pack.

**Subtotal: ~$100**

---

## Vendor 8: Amazon (~$475)

Commodity parts and tools. Prime-eligible.

### Audio & status indicators
| Item | Brand / Model | Qty | Price | Description & Use |
|------|---------------|-----|-------|---------------------|
| INMP441 I2S MEMS Microphone Module (3-pack) | AITRIP | 1 pack | $9.99 | Voice input for Tier 2 voice-control feature. Three units = one used + two spares. |
| 5mm RGB LED Common Cathode 100pc | CHANZON | 1 | $9.49 | Multi-color status indicators with independent R/G/B PWM control. |
| 5mm LED assortment 450pc (5 colors) | DiCUNO | 1 | $9.99 | Single-color status LEDs (green ready, red error, amber warning, etc). |

### Cooling
| Item | Brand / Model | Qty | Price | Description & Use |
|------|---------------|-----|-------|---------------------|
| **GeeekPi Armor Lite V5 Active Cooler for Pi 5** (B0CNVFCWQR) | GeeekPi | 2 | $17.99 = $35.98 | Low-profile active CPU cooler for Faust + Mephisto. ~14mm total height fits within 32mm shell (vs the rejected ICE Tower at 50-60mm). Connects to Pi 5's dedicated 4-pin fan header for automatic temperature control. |
| Noctua NF-A4x10 5V PWM | Noctua | 3 | $15.95 = $47.85 | 40×10mm premium quiet fans for case-mounted exhaust airflow. Two on Faust, one on Mephisto. Provides enclosure airflow so heat doesn't recirculate. 5V PWM (not 12V) runs from Pi GPIO. |
| Arctic MX-6 Thermal Paste 4g | Arctic | 1 | $7.99 | Thermal interface compound for any chip-to-heatsink mounting needing better contact than included pads. |

### Storage
| Item | Brand / Model | Qty | Price | Description & Use |
|------|---------------|-----|-------|---------------------|
| SanDisk Extreme 256GB microSD (SDSQXA1-256G) | SanDisk | 2 | ~$31 = ~$62 | Faust's primary OS storage + pre-imaged cold spare. 256GB holds OS + agent code + skills + PCAP captures + IQ recordings. A2 V30. |
| SanDisk Ultra 128GB microSD | SanDisk | 1 | ~$32 | Mephisto's OS storage. Lower load than Faust; 128GB sufficient. |
| Samsung BAR Plus 256GB USB 3.1 (Titan Gray) | Samsung | 1 | $39.99 | Portable backup/transfer storage for moving captures off Faust, OS image backups, recovery medium. |

### Power & magnets
| Item | Brand / Model | Qty | Price | Description & Use |
|------|---------------|-----|-------|---------------------|
| Caturledas N42 Neodymium Magnets, 10×3mm disc, 100pc | Caturledas | 1 | $12.99 | Dock alignment magnets. 12 used in 6 pairs to mount Mephisto magnetically to Faust (~4-6kg total hold). |
| ALFA Network AWUS036ACM dual-band AC1200 USB WiFi adapter | ALFA Network | 1 | $49.99 | Primary WiFi recon tool. Realtek RTL8812AU chipset, supports monitor mode and packet injection on both 2.4 GHz and 5 GHz. Pi onboard WiFi cannot do monitor mode on 5 GHz or inject packets. |

### Tools & materials
| Item | Brand / Model | Qty | Price | Description & Use |
|------|---------------|-----|-------|---------------------|
| HPFIX Anti-Static Mat + ESD Wristband + Grounding Wire | HPFIX | 1 | $18.89 | ESD-safe assembly workspace. Silicone heat-resistant mat (932°F) for soldering. |
| ORIA 61-in-1 Precision Screwdriver Set | ORIA | 1 | $11.89 | Assembly tool. 57 precision bits cover Phillips, flathead, Torx, hex sizes. Magnetic tip. |
| HANGLIFE M2.5 Heat-Set Threaded Inserts, 100pc brass | HANGLIFE | 1 | $8.99 | Brass threaded inserts (3.5mm OD × 4mm L) heat-pressed into 3D-printed shell for durable screw threads. Far stronger than self-tapping into PETG. |
| HELIFOUNER M2.5 Brass Standoff Assortment, 242pc | HELIFOUNER | 1 | $12.69 | Brass standoff/spacer kit with male/female threaded ends in various lengths (4-25mm). |
| Overture PETG Filament 1.75mm Black 1kg | Overture | 2 | $14.39 = $28.78 | 3D printer filament for shell prints. PETG selected over PLA for impact resistance, heat tolerance, chemical resistance. Two rolls covers 2-3 Faust iterations + 1-2 Mephisto iterations + waste. |

**Subtotal: ~$475**

### Cancelled from Amazon (full refund processed)
- **GeeekPi ICE Tower Cooler for Pi 5 × 2** — 50-60mm vertical clearance incompatible with Faust's 32mm shell. Replaced with Armor Lite V5 (low-profile, ~14mm).

### Sourced from Harvey Mudd makerspace (not purchased)
- Helping hands with magnifier
- 99% isopropyl alcohol
- Gelid GP-Extreme thermal pads (substituted with Arctic MX-6 paste)
- Oscilloscope, bench power supply, soldering iron, 3D printer

---

## Vendor 9: Pololu (~$41)

Voltage regulator that doesn't reliably appear on Amazon.

| Item | Qty | Price | Description & Use |
|------|-----|-------|---------------------|
| Pololu D36V50F5 5V/5.5A Step-Down Regulator (Item #4091) | 1 | $34.95 | Auxiliary 5V power rail. Takes Faust's 4S battery pack input (~14.8V nominal, range 5.5-50V) and produces clean 5V/5.5A output for peripherals needing clean 5V independent of Pi USB output (LEDs, HackRF when battery-powered, sensors). |
| USPS Priority shipping | | ~$6 | Las Vegas to LA, 2-3 days. |

**Subtotal: ~$41**

---

## Per-Unit Bill of Materials

### Faust (Operator Handheld)

**Compute & display:**
- Raspberry Pi 5, 1GB RAM (+1 cold spare microSD card pre-imaged with OS)
- Waveshare 8" DSI LCD (C) 1280×800 IPS capacitive touch, Rev 2.2
- GeeekPi Armor Lite V5 active cooler
- 2× Noctua NF-A4x10 5V PWM case fans (enclosure exhaust)

**Audio:**
- INMP441 I2S MEMS microphone
- MAX98357A I2S amplifier
- 8Ω mini oval speaker

**Software-defined radio:**
- HackRF Pro (100 kHz – 6 GHz, USB-C)
- 75-1000 MHz telescopic antenna
- 300-1100 MHz telescopic antenna
- 700-5800 MHz antenna
- 6× SMA Female bulkhead adapters + 5× u.fl→SMA pigtails

**WiFi/BLE:**
- ALFA AWUS036ACM USB WiFi adapter
- ESP32-S3 Marauder (USB)

**NFC/RFID/IR/iButton:**
- PN532 (13.56 MHz HF NFC)
- T5577/EM4305 combined LF reader/writer
- RDM6300 (LF reader backup)
- CC1101 + SMA antenna (sub-GHz backup)
- IR LED + TSOP38238 receiver
- DS9092 iButton probe + 5 TM1990 blank keys

**Sensors:**
- u-blox NEO-M9N GPS with antenna
- INA219 (current sensor)
- 3× DS18B20 temperature probes (Pi/Hailo/battery)
- Raspberry Pi Camera Module 3 Standard (rear-facing, VLM)

**Controls:**
- 6× tactile pushbuttons (UI)
- SPST toggle switch (RF kill, from heavy-duty toggle 5-pack)
- DPDT slide switch wired as DPST (master power)
- B10K linear potentiometer + knob (display brightness)

**Status indicators:**
- 4× single-color 5mm LEDs (green/red/amber/purple)
- 1× 5mm RGB common-cathode LED

**Power:**
- Geekworm X1202 4-cell UPS HAT
- 4× Molicel P30B 18650 cells
- Pololu D36V50F5 (auxiliary 5V rail)

**External ports & connectors:**
- USB-C Sunken breakout (charging input)
- Panel-mount USB-A (peripheral passthrough)
- Pre-wired Nano SIM tray (MK2 future-use)

**Shell:**
- Custom 3D-printed Overture PETG matte black, iterated 2-3 times
- M2.5 brass heat-set inserts + standoffs

### Mephistopheles / Mephisto (Navigator Peripheral)

**Compute:**
- Raspberry Pi 5, 16GB RAM
- Raspberry Pi AI HAT+ 2 (Hailo-10H, 40 TOPS, 8GB on-board RAM)
- GeeekPi Armor Lite V5 active cooler
- 1× Noctua NF-A4x10 5V PWM case fan
- AI HAT+ 2's bundled heatsink for Hailo chip

**Display:**
- 0.96" I2C OLED (SSD1306, 128×64) — sourced locally / from makerspace supply

**Status & controls:**
- WS2812 RGB LED — sourced locally
- Soft power button — sourced locally (or from spare tactile button stock)

**Power:**
- Geekworm X1201 2-cell UPS HAT
- 2× Molicel P30B 18650 cells

**Storage:**
- SanDisk Ultra 128GB microSD

**Shell:**
- Custom 3D-printed Overture PETG matte black, iterated 1-2 times

### Dock / Interconnect

- **Magnets:** 12× N42 neodymium 10×3mm disc (6 pairs)
- **Cable:** 100mm slim right-angle USB-C to USB-C (Adafruit 6370) + 1 spare
- **Alignment:** 3D-printed Mephisto-shaped pocket in Faust's back panel (~6mm deep, ~0.3mm tolerance)

### Shared Infrastructure

- **Charging:** 2× Official Raspberry Pi 27W USB-C PD power supplies
- **Backup storage:** Samsung BAR Plus 256GB USB 3.1
- **Dev cable:** CP2102 USB-to-TTL serial (Adafruit 954)
- **Power switching:** 10× IRLZ44N MOSFETs (LED PWM, rail switching)
- **Wire:** UL1007 22AWG 5-color, 10m/roll
- **Connectors:** 460pc JST-XH + Dupont 2.54mm assortment kit

---

## Known gaps / add-on items (not in current orders)

These were identified in post-order codebase audits. All are low-cost and
readily sourced locally:

| Item | Why needed | Approx. cost |
|------|-----------|--------------|
| USB-C to USB-A adapter (male-female) | HackRF Pro (USB-C) into Faust's Pi 5 USB-A ports — Pi 5's only USB-C is used for the Mephisto dock | $3-5 |

---

## Explicit Scope Boundaries (NOT in MK1)

These are intentional omissions for MK1 — possible additions in MK2:

- **No cellular modem** — nano-SIM tray pre-wired for MK2 retrofit
- **No RTL-SDR** — HackRF Pro covers needed range
- **No custom PCB** — all jumper/breakout-based for MK1 (HackBat KiCad files referenced for potential MK2 custom carrier)
- **No backup Pi 5 16GB** — canceled, with Cloud Claude API as fallback if Mephisto fails
- **No spare AI HAT+ 2** — same reasoning
- **No GeeekPi ICE Tower** — replaced with low-profile Armor Lite V5 (form-factor incompatibility)
- **No Helping hands / IPA / Gelid pads** — sourced from Harvey Mudd makerspace
- **No Flipper Zero** — faust IS the Flipper alternative

---

## Critical Sourcing Rules (for any re-orders)

| Component | Approved sources | NEVER from |
|-----------|------------------|------------|
| HackRF | Hacker Warehouse, Adafruit, GSG official reseller list | Amazon (clones common) |
| ESP32 Marauder board | Electronic Cats, JustCallMeKoko (when in stock) | Random Amazon listings |
| 18650 cells | 18650BatteryStore, Liion Wholesale, IMR, Battery Junction | Amazon (~30% counterfeit rate) |
| Waveshare displays | Waveshare direct (Rev 2.2+ verified), Freenove as backup | Amazon third-parties (old stock risk) |
| microSD cards | Amazon-fulfilled, SanDisk official, B&H | Random third-party sellers |
| Noctua, Samsung | Amazon-fulfilled (counterfeit risk low for these brands) | Unknown marketplace sellers |
| AI HAT+ 2 | Adafruit, PiShop.us, Raspberry Pi authorized resellers | Random listings |
| Pololu regulators | Pololu direct, Adafruit (limited selection) | Amazon (often unavailable) |

---

## Arrival Timeline & Build Plan

| Week | Dates | Arriving | Build Focus |
|------|-------|----------|-------------|
| **W1** | Apr 14-20 | Amazon (Apr 14-15), Waveshare DHL (~Apr 17-18), Adafruit (~Apr 16-18), Electronic Cats (~Apr 18-22), Pololu (~Apr 16-18) | Infrastructure firmware (agent loop, skill loader, disclosure layer, UI skeleton), OS prep on Pi 5 1GB + 16GB. Thermal tests. Waveshare display bring-up. |
| **W2** | Apr 21-27 | AliExpress trickle (~Apr 22-28), 18650BatteryStore (~Apr 22-25), Geekworm (~Apr 22-28) | Breadboard first assembly. Power subsystem integration. First WiFi/BLE/NFC skills. Shell print v1. |
| **W3** | Apr 28 – May 4 | **HackRF Pro arrives (~Apr 27 – May 11 range)** | Integrate SDR. Finish skills (WiFi, BLE, SDR, NFC). Build 6 Pursuits. Shell v2. Mephisto OLED dashboard. Docked UI. |
| **W4** | May 5-11 | — | Field testing, bug fixing, shell v3 if needed, demo prep. |
| **Buffer** | May 12-15 | — | Reserved for failures, last-minute fixes. |

**Highest risk item:** HackRF Pro backorder. If it doesn't ship by ~Apr 27, SDR skills need to be developed with stubs + recorded IQ files until hardware arrives.

---

## Grand Total

**~$2,059** — under the $2,250 working budget by ~$191. Remaining buffer reserved for contingencies (filament re-order for extra iterations, replacement fan if one DOAs, shipping variance).

**Hardware ordering: COMPLETE.** Firmware development can begin Week 1 (Apr 14) while parts ship.
