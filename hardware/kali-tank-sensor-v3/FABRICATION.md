# Kali tank sensor rev 3 — fabrication package

Generated 2026-09-08 (rev 3.1 layout: 55 × 52 mm, compacted from the first 80 × 55 mm
pass). **Verified: KiCad DRC 0 errors, 0 unconnected items; ERC 0 errors.**

## PCBWay order parameters

| Setting | Value |
|---|---|
| Layers | **4** |
| Size | 55 × 52 mm |
| Quantity | 5 |
| Thickness | 1.6 mm |
| Min track / spacing | 0.25 mm / 0.15 mm (inside the standard 6 mil tier) |
| Min hole | 0.35 mm |
| Surface finish | ENIG (recommended — marine, and better for the 0.5 mm-pitch INA238) |
| Solder mask | any; **green reads best under conformal coat** |
| Assembly | SMT top side only, **excluding U1 and U3** (hand-soldered after delivery) |

Gerbers, drill files and the pick-and-place CSV are in `gerbers/`.

Four layers rather than two: it gives a solid ground plane (In1) directly under the
INA238 and the switching regulator, and a 3V3 plane (In2). On two layers the +3V3,
NODE_A and I2C nets form a knot that needs a via maze to resolve — the plane pair
removes the two largest nets from the routing problem entirely.

## Before powering the first board

1. ~~Verify the DC/DC module's corner pinout.~~ **Done 2026-09-08.** Both variants
   (green `DSN-MINI-360` and black `EY9 3.3V`) have an identical pad map and negligible
   size difference. On the bottom face: **IN+ top-left, OUT+ top-right, IN− bottom-left,
   OUT− bottom-right** — the 14.5/15.0 mm pitch separates IN from OUT, the 8.5 mm pitch
   separates + from −. The footprint is drawn for the module mounted label-side-down and
   viewed from above, which mirrors that: **IN+ is the LOWER-LEFT pad** (also on the
   silkscreen). One footprint takes both variants.
2. **Still confirm IN− and OUT− are one net** (non-isolated buck) with a meter — the
   footprint ties both to the ground plane.
3. Use the **fixed 3.3 V** variant in production. The adjustable one depends on a
   trimpot that is unreachable once potted and can drift.

## Assembly order

1. PCBWay assembles all SMD parts except U1 and U3.
2. **Flash the XIAO before soldering it down** — after assembly, USB needs SB1 opened.
3. Solder U3 (DC/DC module) onto the four oblong pads. They accept both the 14.5 mm
   and 15.0 mm corner pitch and stand ~1 mm proud of the module so an iron reaches them.
4. Solder U1 (XIAO) flat onto its land pattern. Pads stand 1.1 mm proud of the module
   outline — solder from the side, no standoffs needed.
5. Attach and secure the U.FL antenna **before potting**, and route the pigtail out
   of the pour.
6. Wires to J1–J4, each anchored through its 2.2 mm strain-relief hole.

## SB1

Normally **closed**, feeding the buck's 3.3 V into the XIAO's 3V3 pad. **Open it before
connecting USB** — otherwise USB power back-feeds through the module into the 12 V
harness. After potting, USB is unusable anyway and recovery is BLE-triggered OTA.

## Known-good design decisions worth not undoing

- `MSOP-10_3x3mm_P0.5mm` for the INA238, not KiCad's default TSSOP-10. The datasheet's
  DGS0010A drawing cites JEDEC MO-187 variation BA, which is the MSOP footprint.
- I2C pull-ups (R5/R6) go to **VS_INA**, the GPIO10-switched rail — not to +3V3.
  On the always-on rail they would forward-bias the INA238's input protection while
  it is unpowered in deep sleep.
- The 0.15 mm clearance rule exists only because the INA238's own MSOP land has
  0.15 mm pad gaps at 0.5 mm pitch. No track is narrower than 0.2 mm.
