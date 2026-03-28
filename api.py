"""Constants for the STEIN integration."""

DOMAIN = "stein"
CONF_API_TOKEN = "api_token"
CONF_BU_IDS = "bu_ids"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_WEBHOOK_ENABLED = "webhook_enabled"

DEFAULT_SCAN_INTERVAL = 300  # 5 Minuten – Rate-Limit beachten (max 20 req/min)
DEFAULT_API_BASE = "https://stein.app/api"  # Basis, Pfade beginnen mit /api/ext/...

ATTR_LABEL = "label"
ATTR_NAME = "name"
ATTR_STATUS = "status"
ATTR_COMMENT = "comment"
ATTR_CATEGORY = "category"
ATTR_RADIO_NAME = "radio_name"
ATTR_ISSI = "issi"
ATTR_OPERATION_RESERVATION = "operation_reservation"
ATTR_HU_VALID_UNTIL = "hu_valid_until"
ATTR_LAST_MODIFIED = "last_modified"
ATTR_LAST_MODIFIED_BY = "last_modified_by"
ATTR_BU_ID = "bu_id"
ATTR_GROUP_ID = "group_id"

# Asset status values
STATUS_READY = "ready"
STATUS_NOTREADY = "notready"
STATUS_SEMIREADY = "semiready"
STATUS_INUSE = "inuse"
STATUS_MAINT = "maint"

STATUS_LABELS = {
    STATUS_READY: "Einsatzbereit",
    STATUS_NOTREADY: "Nicht einsatzbereit",
    STATUS_SEMIREADY: "Bedingt einsatzbereit",
    STATUS_INUSE: "Im Einsatz",
    STATUS_MAINT: "In Wartung",
}
