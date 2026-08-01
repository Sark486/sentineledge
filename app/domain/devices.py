"""Device-domain constants shared across the service layer."""

from app.domain.intervals import ONLINE_WINDOW

# The location a device is filed under until someone assigns it a real one.
# Also the value written to `ClimateReading.location_snapshot` for such a device.
DEFAULT_LOCATION_NAME = "Unknown"

# How often a reporting device rewrites `last_seen`. Must stay comfortably under
# ONLINE_WINDOW, or a device that is publishing normally would still read as
# offline between refreshes.
LIVENESS_REFRESH = ONLINE_WINDOW / 2
