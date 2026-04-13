# Chunk 4 — Bill of Materials (Under $1000)

**Project:** AI-native pentesting handheld
**Chunk status:** Complete
**Date:** April 11, 2026
**Framing note:** Per chunk 3’s open-ended compute decision, this BOM is structured as four parallel paths (A / B / C / F) rather than a single canonical list. Shared parts are priced once in §3 and not duplicated per-path. All prices in USD, captured April 11, 2026. **Prices are volatile right now** — see §2 for why — so treat totals as ±15%.

-----

## 1. The four paths, priced at a glance

|Path                                                     |Compute core                |Core total|Full BOM v1 target|Headroom under $1000|
|---------------------------------------------------------|----------------------------|----------|------------------|--------------------|
|**A** — Pi 5 + Hailo AI HAT+ 2                           |$225                        |~$570     |~$700 with buffer |~$300               |
|**B** — Pi 5, CPU-only                                   |$95                         |~$440     |~$560 with buffer |~$440               |
|**C** — Orange Pi 5 Max + rkllama                        |$150                        |~$495     |~$620 with buffer |~$380               |
|**F** — Thin-client handheld (LLM on paired phone/laptop)|$45 (Pi Zero 2W or Pi 5 1GB)|~$340     |~$440 with buffer |~$560               |

The paths diverge on compute and a few dependent choices; everything else (RF tooling, battery, shell, consumables) is common and called out once.

-----

## 2. Price volatility — the honest part

Three independent shocks hit Pi pricing between Dec 2025 and Feb 2026:

- **Raspberry Pi 5 16GB jumped from $120 to $205 MSRP** (reported by Tom’s Hardware, Feb 2, 2026) due to LPDDR4 memory cost pressure driven by AI infrastructure demand
- Raspberry Pi introduced a new 1GB Pi 5 variant at $45 (Dec 2025) as a price-floor response
- Compute Module prices rose proportionally

**What this means for this BOM:**

- All Pi 5 pricing in this chunk reflects the Feb 2026 increase
- Numbers may move again before you order — check `rpilocator.com` day-of-purchase
- The Hailo AI HAT+ 2 has held at $130 MSRP (less memory-exposed)
- Rockchip boards (Option C) are less affected by the LPDDR4 squeeze
- Budget for ±15% on SBC + memory-heavy components, ±5% on everything else

I’ve flagged `[volatile]` on line items where current pricing is likely to shift before May 15.

-----

## 3. Common parts (needed regardless of path)

### 3a. Wireless RF tooling — ESP32-based (common to all paths)

The RF layer doesn’t touch the host SBC directly — it communicates over USB-serial. This means it’s path-independent and portable across A/B/C.

|Part                                                                    |Purpose                                             |Source                                    |Price     |Notes                                                                                                                                                          |
|------------------------------------------------------------------------|----------------------------------------------------|------------------------------------------|----------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
|ESP32-S3 Marauder board (Flipper WiFi Dev Board Pro clone or equivalent)|WiFi + BLE recon, deauth, PMKID capture, Evil Portal|JustCallMeKoko / Hacker Warehouse / Amazon|**$25–40**|Skip the actual Flipper Zero — the Marauder firmware runs on bare ESP32-S3 boards. Choose one with microSD slot onboard so you don’t have to solder a breakout.|
|MicroSD card for ESP32 (32GB max)                                       |PCAP capture storage                                |Any                                       |~$8       |Marauder caps at 32GB                                                                                                                                          |
|USB-C to micro-USB cable (short, 6”)                                    |ESP32 ↔ Pi                                          |Any                                       |~$4       |Or USB-C-to-USB-C depending on board                                                                                                                           |
|2.4GHz antenna (u.fl to SMA pigtail, optional)                          |Better range for Marauder                           |Adafruit / Amazon                         |~$6       |Only if your chosen board has u.fl connector                                                                                                                   |

**Subtotal RF core: ~$45**

### 3b. Sub-GHz / NFC / IR (summer work, skippable for v1)

Chunk 1’s survey flagged HackBat’s CC1101 + PN532 combo as the reference design. For v1 by May 15, I’d recommend *not* including these — the ESP32 WiFi/BLE layer alone is enough for a useful functional demo, and sub-GHz adds FCC scrutiny you want to defer until the disclosure model is proven. Pricing here for when you add them in summer:

|Part                                       |Price|Notes       |
|-------------------------------------------|-----|------------|
|CC1101 module (sub-GHz 315/433/868/915 MHz)|$6–12|SPI to ESP32|
|PN532 module (NFC 13.56MHz)                |$8–15|I2C to ESP32|
|IR LED + receiver pair                     |~$3  |GPIO driven |
|433MHz rubber-duck antenna                 |~$8  |SMA         |

**Summer add-on subtotal: ~$30–40**. Not counted in v1 totals.

### 3c. Power subsystem (common to A / B / C)

|Part                                                   |Purpose                       |Source                              |Price     |Notes                                                                                           |
|-------------------------------------------------------|------------------------------|------------------------------------|----------|------------------------------------------------------------------------------------------------|
|**Geekworm X1202 4-Cell 18650 UPS HAT** (or equivalent)|Battery + 5.1V 5A UPS for Pi 5|Geekworm / Amazon                   |**$32–40**|Use this for A, B, C. Pi 5 peak draw under load + HAT approaches 20W, so 5A rating is mandatory.|
|4× Samsung/LG 18650 cells (3500mAh each)               |Battery cells                 |Battery Junction / 18650BatteryStore|**$32–40**|Avoid cells with built-in protection PCBs — UPS HAT handles protection.                         |
|Official Raspberry Pi 27W USB-C PD power supply        |Wall charging                 |Adafruit                            |**$12**   |Required — cheaper supplies cause PMIC resets under combined Pi+HAT load.                       |

**Subtotal power: ~$85**

### 3d. Display (path-specific note)

|Part                                                   |Purpose             |Source                                            |Price     |Notes                                                                                  |
|-------------------------------------------------------|--------------------|--------------------------------------------------|----------|---------------------------------------------------------------------------------------|
|**Waveshare 5” DSI capacitive touch display (800×480)**|Primary UI, path A/B|Waveshare / Amazon                                |**$40–50**|DSI plug-and-play on Pi 5 with Rev 2.2 boards. Watch for Rev 2.1 short-detection issue.|
|Pi 5 DSI FPC cable (22-pin to 15-pin)                  |Display connection  |Raspberry Pi official / Adafruit                  |**$1–2**  |Pi 5 uses 22-pin; older 15-pin cables won’t work.                                      |
|**Freenove 5” touchscreen** (alternative)              |Same function       |Freenove store                                    |~$40      |Bundle includes multiple cable lengths                                                 |
|Option C (Orange Pi 5 Max) display                     |Same function       |Waveshare has HDMI and MIPI DSI options for RK3588|$45–55    |Slightly more expensive due to less standardization                                    |

**Subtotal display: ~$45** (path A/B) or ~$55 (path C)

### 3e. Storage

|Part                                   |Source|Price  |Notes                                                                                           |
|---------------------------------------|------|-------|------------------------------------------------------------------------------------------------|
|SanDisk Extreme 128GB microSD (A2, V30)|Amazon|**$18**|For OS + models + PCAP captures. 64GB works for v1 but models eat space.                        |
|Optional: USB 3.0 flash drive 128GB    |      |$15    |If NVMe is blocked (it is, for Option A due to PCIe contention), USB storage is the upgrade path|

**Subtotal storage: ~$18 for v1, +$15 if you want expansion**

### 3f. Enclosure and physical

|Part                                       |Purpose               |Source                                    |Price                  |Notes                                                                |
|-------------------------------------------|----------------------|------------------------------------------|-----------------------|---------------------------------------------------------------------|
|3D-printed enclosure (PETG or ABS filament)|Shell                 |Harvey Mudd makerspace or personal printer|**$8–15** filament cost|Iterate 2-3 versions before May 15. Budget time more than money here.|
|M2.5 standoff kit + screws                 |Assembly              |Amazon                                    |**$10**                |8-30mm lengths, brass preferred                                      |
|Active cooling fan for Pi 5                |Thermal               |Raspberry Pi official active cooler       |**$5**                 |Mandatory for any path that uses Pi 5 under sustained load           |
|Heatsink for Hailo (path A only)           |Thermal               |Included with AI HAT+ 2                   |$0                     |                                                                     |
|Physical buttons (6× tactile)              |Kill switch, mode, nav|Adafruit / Digi-Key                       |**$4**                 |Wired to GPIO                                                        |
|Toggle switch (SPST)                       |Hardware RF kill      |Any                                       |**$3**                 |Cuts power to ESP32 explicitly                                       |
|Wire, solder, heatshrink, misc             |Assembly              |Makerspace stock or ~$15                  |**$15**                |                                                                     |

**Subtotal enclosure: ~$45–55**

### 3g. Development & debug (own-it-once, already have most)

|Part                         |Source  |Price|Notes                                           |
|-----------------------------|--------|-----|------------------------------------------------|
|USB-UART FTDI cable          |Adafruit|$10  |For ESP32 debug / Pi serial console             |
|Second microSD card (dev)    |Any     |$10  |For experimentation without killing your main OS|
|HDMI cable + adapter         |Any     |$8   |Development/debug bench use                     |
|Logic analyzer (Saleae clone)|Amazon  |$15  |Nice-to-have for I2C/SPI debug                  |

**Subtotal dev: ~$45** — call $0 if you already have these, otherwise ~$45.

### 3h. Shared subtotal (every path includes this)

**$45 (RF) + $85 (power) + $18 (storage) + $45–55 (enclosure) + ~$45 (display, path-dependent) = ~$240–250 common**

-----

## 4. Path A — Pi 5 + Hailo AI HAT+ 2

### Path-specific parts

|Part                                          |Source              |Price                              |Notes                                                                               |
|----------------------------------------------|--------------------|-----------------------------------|------------------------------------------------------------------------------------|
|**Raspberry Pi 5 — 8GB RAM** [volatile]       |Adafruit / PiShop.us|**~$95** (up from $80 pre-Feb 2026)|Could be 4GB for $75 since Hailo holds model; 8GB gives room for agent + OS + scans.|
|**Raspberry Pi AI HAT+ 2 (40 TOPS Hailo-10H)**|Adafruit / PiShop.us|**$130**                           |MSRP holding. SKU at Adafruit: 6451.                                                |

**Path A compute: ~$225**

### Path A BOM total

|Section                                       |Cost         |
|----------------------------------------------|-------------|
|Compute (Pi 5 8GB + AI HAT+ 2)                |$225         |
|Common shared (§3 subtotal, w/ 5” DSI display)|$240         |
|Dev/debug (if needed)                         |$45          |
|15% buffer for volatile pricing + shipping    |$78          |
|**Path A total**                              |**~$590–700**|

Headroom under $1000: $300–400 for summer add-ons (CC1101, PN532, IR, a Pi Camera Module 3 for VLM work), or pivot budget if the April benchmark goes badly.

### Path A specific gotchas

- AI HAT+ 2 uses Pi 5’s sole PCIe lane → no NVMe SSD possible
- Hailo-ollama doesn’t auto-start → write systemd unit day one
- 15W supply will PMIC-reset → the 27W PD supply is not optional
- Thermal: Pi 5 active cooler + Hailo heatsink both needed under sustained load

-----

## 5. Path B — Pi 5, CPU-only

### Path-specific parts

|Part                                   |Source              |Price   |Notes                                                                                                                                                       |
|---------------------------------------|--------------------|--------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
|**Raspberry Pi 5 — 8GB RAM** [volatile]|Adafruit / PiShop.us|**~$95**|8GB gives room for model + KV cache + OS + agent + UI. 4GB is too tight. 16GB ($205) only if you want 7B-class models at ~1 tok/sec — probably not worth it.|

**Path B compute: ~$95**

### Path B BOM total

|Section                                       |Cost                        |
|----------------------------------------------|----------------------------|
|Compute (Pi 5 8GB alone)                      |$95                         |
|Common shared (§3 subtotal, w/ 5” DSI display)|$240                        |
|Optional NVMe M.2 HAT + 256GB SSD             |+$45 (HAT) + $25 (SSD) = $70|
|Dev/debug (if needed)                         |$45                         |
|15% buffer                                    |$56                         |
|**Path B total**                              |**~$435–560**               |

Headroom under $1000: $440–565. By far the most budget breathing room of any path.

### Path B specific notes

- $130 saved vs Path A
- NVMe option adds speed and reduces SD wear; sensible for a research device that writes lots of PCAPs
- Model flexibility is the biggest non-price win: you can run Qwen2.5, Qwen3, Llama 3.x, Phi-4, lfm2.5, anything new that arrives
- CPU contention with UI/scans is the biggest non-price cost

-----

## 6. Path C — Orange Pi 5 Max + rkllama

### Path-specific parts

|Part                                                      |Source                          |Price       |Notes                                                                                                            |
|----------------------------------------------------------|--------------------------------|------------|-----------------------------------------------------------------------------------------------------------------|
|**Orange Pi 5 Max 16GB**                                  |AliExpress / Arace Tech / Amazon|**$140–165**|16GB is the right call here — W8A8 quantization means bigger model files than Hailo’s W4A8, so you need headroom.|
|Display: 5” DSI or HDMI touchscreen compatible with RK3588|Waveshare                       |**$50–55**  |Slightly more expensive than Pi DSI due to less standardization. HDMI option is cheapest and most compatible.    |
|Heatsink + fan for RK3588                                 |Orange Pi official or 3rd party |$8–12       |RK3588 runs hot under NPU load                                                                                   |

**Path C compute: ~$150**

### Path C BOM total

|Section                                                                                           |Cost         |
|--------------------------------------------------------------------------------------------------|-------------|
|Compute (Orange Pi 5 Max 16GB)                                                                    |$150         |
|Display + cabling (RK3588-specific, slightly more than Pi)                                        |$55          |
|Power subsystem (§3c — UPS HATs for Orange Pi exist but are less common; budget $45 vs $40 for Pi)|$90          |
|RF core (§3a — unchanged, USB-attached ESP32)                                                     |$45          |
|Storage (§3e)                                                                                     |$18          |
|Enclosure (§3f — dimensions differ slightly from Pi)                                              |$50          |
|Dev/debug (if needed)                                                                             |$45          |
|15% buffer                                                                                        |$65          |
|**Path C total**                                                                                  |**~$480–620**|

Headroom under $1000: $380–520.

### Path C specific notes

- Biggest win: `rkllama` has tool/function calling already wired for Qwen and Llama 3.2+ — saves a few days of integration
- Biggest cost: Pi HATs do not work on Orange Pi. UPS, display, enclosure all need RK3588-compatible alternatives
- Your ESP32 RF tooling runs over USB, so it’s unaffected by the host swap
- Camera ecosystem is weaker — if VLM/camera work is in your plans, this is friction
- Community is smaller; expect more forum-diving for weird problems

-----

## 7. Path F — Thin-client handheld (LLM on paired phone/laptop)

### Path-specific parts

|Part                                    |Source  |Price  |Notes                                                                               |
|----------------------------------------|--------|-------|------------------------------------------------------------------------------------|
|**Raspberry Pi 5 — 1GB RAM** [volatile] |Adafruit|**$45**|New low-end SKU released Dec 2025. Perfect for a thin client — doesn’t need LLM RAM.|
|Or: **Raspberry Pi Zero 2W**            |Adafruit|**$15**|Even smaller, sufficient if you’re okay with a smaller display and lighter UI.      |
|LLM runs on user’s existing phone/laptop|—       |$0     |You don’t spec the LLM compute — the user provides it.                              |

**Path F compute: $15–45**

### Path F BOM total

|Section                                                                |Cost         |
|-----------------------------------------------------------------------|-------------|
|Compute (Pi 5 1GB)                                                     |$45          |
|Display (same 5” DSI)                                                  |$45          |
|Power (lighter — can use a smaller 2-cell UPS since draw is much lower)|$35          |
|RF core (§3a)                                                          |$45          |
|Storage (§3e)                                                          |$18          |
|Enclosure (§3f — can be smaller)                                       |$40          |
|Dev/debug (if needed)                                                  |$45          |
|15% buffer                                                             |$40          |
|**Path F total**                                                       |**~$320–440**|

Headroom under $1000: $560–680.

### Path F specific notes and architecture cost

- **This changes the project’s pitch.** “Local-LLM handheld” becomes “local-network LLM agent with RF handheld front-end.” That’s defensible but different.
- Handheld is small, cool, long battery life, cheap
- Requires pairing UX (Bluetooth / WiFi direct / local network discovery)
- Trust boundary question: what if the paired device is compromised? Worth thinking through.
- Network latency between devices affects agent feel
- If you go this way, consider making the paired-device requirement *optional* — fall back to a tiny local model (Qwen2.5 0.5B at ~20 tok/sec on Pi 5 CPU) when no paired device is present, run the “real” LLM on phone/laptop when available

-----

## 8. Summary table — all four paths side by side

|Line item                                 |A (Pi+Hailo)    |B (Pi CPU)    |C (Orange Pi 5 Max)        |F (thin client)|
|------------------------------------------|----------------|--------------|---------------------------|---------------|
|SBC                                       |Pi 5 8GB — $95  |Pi 5 8GB — $95|Orange Pi 5 Max 16GB — $150|Pi 5 1GB — $45 |
|Accelerator                               |AI HAT+ 2 — $130|—             |(built-in NPU)             |—              |
|Display                                   |5” DSI — $45    |5” DSI — $45  |RK3588-compat 5” — $55     |5” DSI — $45   |
|Power (UPS + cells + PSU)                 |$85             |$85           |$90                        |$35            |
|RF (ESP32 Marauder + SD + cable + antenna)|$45             |$45           |$45                        |$45            |
|Storage (SD)                              |$18             |$18           |$18                        |$18            |
|Enclosure                                 |$50             |$50           |$50                        |$40            |
|Dev/debug (if needed)                     |$45             |$45           |$45                        |$45            |
|**Core subtotal**                         |**~$513**       |**~$383**     |**~$453**                  |**~$273**      |
|15% volatile buffer                       |$77             |$57           |$68                        |$41            |
|**Total (including buffer)**              |**~$590**       |**~$440**     |**~$521**                  |**~$314**      |
|Headroom under $1000                      |~$410           |~$560         |~$479                      |~$686          |

-----

## 9. Custom-protoboard / wiring flags

None of these paths require a custom PCB for v1. **All connections can be made with jumpers, breakouts, and off-the-shelf cables.**

Custom protoboard work would only become warranted if:

- You add the CC1101 + PN532 + IR stack in summer → then an adapter board for ESP32-S3 that presents all three peripherals cleanly starts to make sense. HackBat’s KiCad files (from chunk 1) are the reference.
- You want to shrink the form factor for v2 → custom carrier board that hosts Pi CM5 + Hailo M.2 + ESP32 + battery management, all in one PCB. Substantial project.

**For v1 build-by-May-15, recommend: all breakouts, all jumper wires, no custom PCB.** 3D-printed shell handles mechanical integration. This is the right call under deadline pressure.

-----

## 10. Vendor recommendations and substitutes

### Primary vendors (US-friendly, generally in stock as of April 2026)

- **Adafruit** — Pi 5, AI HAT+ 2, cables, breakouts, hobby parts. Ships fast. Priced at MSRP or close. Good for common parts.
- **PiShop.us** — Full Pi ecosystem with good AI HAT inventory. Often has stock when Adafruit is out.
- **Amazon** — ESP32 boards, 18650 cells, batteries, SD cards, consumables. Watch for counterfeit 18650s — buy from reputable sellers like 18650BatteryStore.
- **Hacker Warehouse** — Specialty pentesting hardware. Where to buy Marauder-compatible boards.
- **JustCallMeKoko LLC** — The Marauder firmware author’s own store — most reliable source for Flipper WiFi Dev Board Pro variants.
- **AliExpress** — Orange Pi 5 Max, RK3588 accessories. Shipping 2-3 weeks; check seller reputation.
- **Waveshare / Freenove** — Touchscreens, display cables, both direct and via Amazon.
- **Geekworm** — UPS HATs, cases, Pi 5 accessories.

### Substitutes / fallbacks if primary is out of stock

|Primary                   |Substitute                                                                                         |
|--------------------------|---------------------------------------------------------------------------------------------------|
|Pi 5 8GB at Adafruit      |CanaKit, PiShop, or ThePiHut (check rpilocator.com)                                                |
|Official AI HAT+ 2        |No substitute — only one vendor                                                                    |
|Flipper WiFi Dev Board Pro|Electronic Cats ESP32-S3 Marauder Add-On, or generic ESP32-S3 DevKitC board + manual Marauder flash|
|Waveshare 5” DSI          |Freenove 5”, OSOYOO 5” DSI, SunFounder 5” DSI-IPS                                                  |
|Geekworm X1202 UPS        |Waveshare UPS HAT (B), DFRobot Pi 5 UPS HAT                                                        |

-----

## 11. What’s NOT in this BOM (intentional omissions)

These are worth calling out because they might feel missing:

- **No Pi Camera Module.** Camera/VLM is summer work per scope. Add when you’re ready (~$25 for Pi Camera Module 3).
- **No GPS.** Not in v1 scope. ~$15 if needed.
- **No dedicated microphone.** Speech-to-text wasn’t in the v1 feature list. Add a USB mic ~$10 if you want voice input.
- **No speakers.** Audio output not in v1 scope. Add a small I2S DAC + speaker ~$15 if needed.
- **No LTE / cellular modem.** Handheld is WiFi-only for v1 (connects to hotspot or operates offline).
- **No custom PCB.** See §9 — not warranted for v1.
- **No lab equipment** (oscilloscope, power supply, soldering iron, 3D printer). Harvey Mudd makerspace access covers this.
- **No backup device.** If the only Pi dies a week before deadline, you’re in trouble — consider buying a second Pi 5 4GB ($75) as spare. Not in core BOM but worth a thought.

-----

## 12. Ordering sequence recommendation

Time-to-arrival matters for a May 15 deadline. Suggested order:

**Week of April 14 (now):**

- Pi 5 8GB + AI HAT+ 2 (or whichever compute path you choose) — longest-lead items, order first
- Waveshare 5” DSI display + cable — check Rev 2.2 specifically
- UPS HAT + 18650 cells + PD power supply
- microSD cards (buy two)
- ESP32-S3 Marauder board + USB cable

**Once compute arrives (~1 week):**

- Benchmark Qwen2.5 1.5B on your chosen hardware against a realistic agent prompt. This is the go/no-go for the chosen path per chunk 3’s recommendation.
- If benchmark fails Path A → place Path C order within 48 hours to preserve deadline

**Once benchmark validated:**

- Enclosure hardware (standoffs, screws, switches, buttons)
- Filament for 3D printing
- Any missing dev tools

-----

## 13. References (primary pricing sources)

- Raspberry Pi 5 price increase news — https://www.tomshardware.com/raspberry-pi/raspberry-pi-5-price-increases-drastically-as-ai-shortage-bites-16gb-version-now-usd205-second-price-increase-in-three-months-over-70-percent-more-expensive-than-original-msrp
- Pi 5 1GB release — https://blog.adafruit.com/2025/12/01/1gb-raspberry-pi-5-released-at-45-as-memory-driven-prices-rise/
- AI HAT+ 2 product page — https://www.raspberrypi.com/products/ai-hat-plus-2/
- AI HAT+ 2 at Adafruit — https://www.adafruit.com/product/6451
- AI HAT+ 2 at PiShop — https://www.pishop.us/product/raspberry-pi-ai-hat-2/
- Geekworm X1202 UPS — https://geekworm.com/products/x1202
- Waveshare 5” DSI touchscreen — https://www.waveshare.com/5inch-dsi-lcd.htm
- ESP32 Marauder project — https://github.com/justcallmekoko/ESP32Marauder
- JustCallMeKoko Marauder board — https://justcallmekokollc.com/products/flipper-zero-wifi-dev-board-pro
- Electronic Cats Marauder Add-on — https://electroniccats.com/store/flipper-add-on-marauder/
- Rpilocator (stock check) — https://rpilocator.com

-----

**Next chunk:** Week-by-week build plan through May 15, agent skill/tool architecture, and disclosure layer implementation sketch. With compute path chosen via the April benchmark, the build plan becomes concrete (install → skills → disclosure → UI → enclosure → field test).