from __future__ import annotations

DOMAIN = "bluestream_acm200"

CONF_HOST = "host"
CONF_PORT = "port"

CONF_NUM_INPUTS = "num_inputs"
CONF_NUM_OUTPUTS = "num_outputs"

CONF_POLL_INTERVAL = "poll_interval"

# Friendly naming
CONF_INPUT_NAMES = "input_names"     # mapping: {"1": "Apple TV", ...}
CONF_OUTPUT_NAMES = "output_names"   # mapping: {"1": "Bedroom TV", ...}

DEFAULT_PORT = 23
DEFAULT_NUM_INPUTS = 4
DEFAULT_NUM_OUTPUTS = 9
DEFAULT_POLL_INTERVAL = 5  # seconds

PLATFORMS = ["select", "media_player", "sensor"]
