# Blustream ACM200

This custom integration adds support for the **Blustream ACM200 video matrix** to Home Assistant.

The integration connects directly to the ACM200 over the local network and does not require any cloud services. Device state is retrieved by polling the unit at regular intervals.

---

## Features

* Local network control of the Blustream ACM200 video matrix
* Configuration via the Home Assistant UI (Config Flow)
* Media Player entities for zone/output control
* Sensor entities for device and zone status
* Select entities for input and routing selection
* No cloud dependency

---

## Installation

### HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Open the menu (three dots, top right) and select **Custom repositories**
4. Add this repository URL:

   ```
   https://github.com/Bobby5291/bluestream_acm200
   ```
5. Select category **Integration**
6. Install the integration
7. Restart Home Assistant

---

## Configuration

After installation:

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **Blustream ACM200**
4. Follow the on-screen setup instructions

All configuration is handled via the Home Assistant UI.

---

## Entities

The integration creates the following entity types:

### Media Player

* Output / zone control
* Input (source) selection
* Power and routing control (where supported)

### Sensors

* Device status information
* Connection and zone-related state values

### Select

* Input routing
* Operating modes (where applicable)

---

## Communication

This integration communicates with the Blustream ACM200 using **local polling**.
Home Assistant periodically queries the device to retrieve the current state.

---

## Requirements

* A Blustream ACM200 accessible on the local network
* Home Assistant 2023.1.0 or newer

---

## Disclaimer

This is an independent, community-developed integration and is not affiliated with or endorsed by Blustream.

