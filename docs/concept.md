# Concept — XIAO ESP32-C3 BLE tank sensor

## Purpose

The tank sensor is a sealed, maintenance-free node based on a Seeed
Studio XIAO ESP32-C3. It measures a conventional resistive tank sender,
derives the tank level locally, and reports the result to Home Assistant
using BTHome BLE advertisements.

The design deliberately does not depend on Wi-Fi for normal operation.
On a boat, the Wi-Fi infrastructure may be switched off to save energy.
Wi-Fi is therefore used only when a firmware update is required.

The completed sensor may be installed in a sealed enclosure and fully
potted in resin. Normal operation and firmware maintenance must
consequently require no physical access.

## Hardware Concept

The node consists of:

-   XIAO ESP32-C3
-   I2C voltage/current measurement device
-   Measurement circuit for the variable-resistance tank sender
-   Switchable measurement electronics where useful to reduce standby
    consumption
-   Boat power supply interface
-   No buttons, connectors, or other physical controls required after
    installation

The tank sender itself is treated simply as a variable resistor. The
ESP32 derives its resistance from the measured voltage and current.

## Normal Operating Cycle

The sensor spends most of its time in deep sleep.

Approximately every 10 seconds it wakes and performs one measurement
cycle:

1.  Wake from deep sleep.
2.  Power or enable the measurement circuitry if it was switched off.
3.  Read voltage and current repeatedly over I2C for approximately 2--3
    seconds.
4.  Calculate the sender resistance.
5.  Filter the measurements to suppress electrical noise, sender noise,
    and short-term effects caused by vessel motion and liquid sloshing.
6.  Validate the result and reject implausible readings, open circuits,
    short circuits, and transient outliers.
7.  Update the learned sender range where appropriate.
8.  Map the filtered resistance to a tank level between 0 and 100%.
9.  Transmit the resulting level using BTHome BLE advertisements.
10. Briefly scan for the dedicated BLE OTA trigger.
11. If no OTA trigger is detected, persist changed long-term state when
    necessary and return to deep sleep.

Several BTHome advertisements should be transmitted during the wake
period rather than relying on a single BLE packet. Missing an individual
measurement is acceptable because tank level changes slowly.

## Automatic Tank Calibration

The sensor requires no tank-specific configuration.

It learns the useful resistance range of the installed sender over time.
Persistent state includes at least:

-   Learned minimum resistance
-   Learned maximum resistance
-   Relevant calibration confidence/state
-   Last known valid tank level
-   Diagnostic/fault state where useful

The learning algorithm must not simply accept every all-time minimum and
maximum. New extrema should be sanitized and accepted conservatively.

The implementation should:

-   Filter measurements before using them for calibration.
-   Reject electrically implausible values.
-   Reject isolated spikes and unrealistic changes.
-   Require repeated or sufficiently stable observations before
    accepting significant new extrema.
-   Expand the learned range conservatively.
-   Avoid automatically shrinking the learned range because normal
    operation may not visit empty or full for long periods.
-   Persist learned calibration across deep sleep and power cycles.

The resulting filtered resistance is mapped directly onto the learned
range to produce a clamped 0--100% tank-level value. The mapping
direction can be automatically handled or fixed according to the sender
characteristics.

Broad initial assumptions may be used before both real extrema have been
observed, but normal operation should progressively improve the
calibration without user intervention.

## BTHome and Home Assistant

The primary BLE output is a standard BTHome percentage measurement
representing tank level.

Home Assistant can receive this through its native Bluetooth/BTHome
support, directly or through Bluetooth proxies. No tank-specific Home
Assistant integration is required.

The normal production payload should remain small. The essential value
is:

-   Tank level: 0--100%

Development firmware may additionally advertise diagnostic information
such as raw resistance or fault state.

All tank interpretation and calibration belongs on the sensor. Home
Assistant should not need to understand the sender resistance or
calibration algorithm.

## BLE-Triggered OTA Mode

Wi-Fi is completely disabled during normal operation.

During every normal wake cycle, the XIAO briefly scans for a predefined
BLE advertisement representing an OTA request.

The OTA trigger is a unique advertisement signature controlled by the
system. A dedicated BLE-capable device near Home Assistant, such as
another XIAO ESP32-C3, can repeatedly transmit this trigger when an
update is requested.

The tank sensor does not need to receive the trigger immediately.
Because it wakes approximately every 10 seconds, the OTA trigger
transmitter should advertise continuously for long enough that the
sensor encounters it during one of its scan windows.

When the trigger is detected, the tank sensor:

1.  Cancels the normal return to deep sleep.
2.  Enables Wi-Fi.
3.  Connects to the configured boat Wi-Fi network.
4.  Starts the OTA service.
5.  Remains awake for a defined OTA maintenance window.
6.  Accepts a firmware update if one is supplied.
7.  Reboots after a successful update.
8.  Returns to normal low-power operation if the OTA window expires
    without an update.

The OTA implementation should include a safe recovery mechanism so that
a failed application startup does not permanently prevent subsequent
firmware updates.

## OTA Trigger Transmitter

A separate BLE node associated with Home Assistant can provide the OTA
trigger.

Its behavior is simple:

1.  Remain idle during normal operation.
2.  When an OTA update is requested, repeatedly transmit the predefined
    BLE OTA-trigger advertisement.
3.  Continue advertising for several minutes or until the target tank
    sensor becomes reachable over Wi-Fi.
4.  Stop advertising after the update operation or timeout.

The exact mechanism by which Home Assistant controls this transmitter is
independent of the tank-sensor protocol and can be implemented later.

## Power Strategy

The fundamental power-management rule is:

**BLE is the always-available communication mechanism; Wi-Fi is a
temporary maintenance mechanism.**

The sensor therefore avoids periodic Wi-Fi association or update
polling. In particular, it does not wake every minute merely to check
whether an update exists.

Normal power consumption consists primarily of:

-   Deep-sleep current
-   Approximately one measurement period every 10 seconds
-   Short BTHome advertising bursts
-   A short BLE scan for the OTA trigger

The comparatively expensive Wi-Fi radio is activated only after an
explicit BLE OTA request.

Further optimization can reduce the active period once practical
measurements establish how long the sender must be sampled to obtain a
sufficiently stable tank-level estimate.

## State Model

The firmware can be represented by four principal states:

`DEEP_SLEEP -> MEASURE -> BLE_ADVERTISE/SCAN -> DEEP_SLEEP`

When an OTA trigger is received:

`BLE_SCAN -> WIFI_OTA -> REBOOT -> normal operation`

This keeps the normal execution path deterministic, short, and
independent of any external network infrastructure.

## Design Principles

-   No physical interaction required after installation.
-   Suitable for a fully sealed and resin-potted enclosure.
-   Wi-Fi-independent normal operation.
-   Home Assistant integration through standard BTHome rather than
    custom HA code.
-   Self-calibrating resistive sender with persistent learned limits.
-   Aggressive use of deep sleep.
-   BLE-triggered, Wi-Fi-based remote firmware updates.
-   Graceful operation when Home Assistant, Bluetooth receivers, or boat
    Wi-Fi are temporarily unavailable.
-   Sensor intelligence remains local so tank measurement continues to
    work independently of the rest of the vessel infrastructure.
