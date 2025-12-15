# bluestream_acm200
Home Assistant integration for the Blustream ACM200 video matrix.

# Blustream ACM200

This custom integration adds support for the Blustream ACM200 video matrix to Home Assistant.

The integration connects directly to the device over the local network and does not require any cloud services. 

## Features

* Local control of the Blustream ACM200
* Configuration via the Home Assistant UI (Config Flow)
* Media Player entities for audio zones
* Sensor entities for device and zone status
* Select entities for input and mode selection

## Installation

1. Open HACS in Home Assistant
2. Go to **Integrations**
3. Add this repository as a **Custom Repository**
4. Install the integration
5. Restart Home Assistant

## Configuration

After installation, add the integration via:

**Settings → Devices & Services → Add Integration**

Follow the on-screen configuration steps.

## Communication

This integration uses local polling to communicate with the device.

## Limitations
Right nbow we ar eunabel to gather the sate of the each receiver and transmitter but this is something I hope to include later on

