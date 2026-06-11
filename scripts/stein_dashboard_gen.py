#!/usr/bin/env python3
"""
STEIN Dashboard Generator – v2 mit Einsatz-Tab
Liest STEIN-Assets und Einsätze aus der HA State Machine
und generiert eine dashboard.yaml mit zwei Views:
  1. Assets (wie bisher)
  2. Einsätze (neu)

Aufruf: python3 /config/scripts/stein_dashboard_gen.py
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
import yaml

# ── Konfiguration ─────────────────────────────────────────────────────────────
HA_URL         = "http://localhost:8123"
TOKEN_FILE     = "/config/scripts/stein_token.txt"
DASHBOARD_FILE = "/config/dashboards/stein.yaml"
VERBINDUNG     = "sensor.stein_api_stein_verbindung"
FILTER_ENTITY  = "input_select.stein_filter"

GROUP_NAMES = {
    1: "Fahrzeuge",
    2: "Geraete",
    3: "Sonderfunktionen",
    4: "Einheiten",
    5: "Anhaenger",
}

STATUS_FILTERS = [
    ("ready",     "Bereit",       "mdi:check-circle", "green"),
    ("semiready", "Bedingt",      "mdi:alert-circle", "orange"),
    ("notready",  "Nicht bereit", "mdi:close-circle", "red"),
    ("inuse",     "Im Einsatz",   "mdi:fire-truck",   "blue"),
    ("maint",     "Wartung",      "mdi:wrench",       "purple"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_token():
    if os.path.exists(TOKEN_FILE):
        return open(TOKEN_FILE).read().strip()
    return os.environ.get("SUPERVISOR_TOKEN", "")


def ha_get_states(token):
    req = urllib.request.Request(
        f"{HA_URL}/api/states",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def find_assets(states):
    all_entity_ids = {s["entity_id"] for s in states}
    asset_sensors = []
    for state in states:
        eid = state["entity_id"]
        attrs = state.get("attributes", {})
        if (eid.startswith("sensor.") and
                eid.endswith("_status") and
                "status_raw" in attrs and
                "bu_id" in attrs):
            asset_sensors.append((eid, attrs))

    assets = []
    for sensor_id, attrs in asset_sensors:
        base = sensor_id[len("sensor."):-len("_status")]
        asset_id = attrs.get("id")
        bu_id = attrs.get("bu_id")
        group_id = attrs.get("group_id", 99)

        SUFFIX_ALIASES = {
            "status_setzen":      ["status_setzen"],
            "einsatzreservierung":["einsatzreservierung"],
            "bezeichnung":        ["bezeichnung", "label"],
            "name":               ["name"],
            "funkrufname":        ["funkrufname", "radioname"],
            "kommentar":          ["kommentar", "comment"],
            "kategorie":          ["kategorie", "category"],
            "issi":               ["issi"],
        }

        def find_entity(domain, suffix):
            aliases = SUFFIX_ALIASES.get(suffix, [suffix])
            for alias in aliases:
                candidate = f"{domain}.{base}_{alias}"
                if candidate in all_entity_ids:
                    return candidate
                if asset_id:
                    candidate2 = f"{domain}.stein_{asset_id}_{alias}"
                    if candidate2 in all_entity_ids:
                        return candidate2
            for s in states:
                eid = s["entity_id"]
                if not eid.startswith(f"{domain}."):
                    continue
                label = attrs.get("label", "")
                for alias in aliases:
                    if (f"stein_{asset_id}_{alias}" in eid or
                            (label and f"_{alias}" in eid and label.lower().replace(" ","_") in eid)):
                        return eid
            return f"{domain}.{base}_{suffix}"

        assets.append({
            "sensor_id": sensor_id,
            "base":      base,
            "asset_id":  asset_id,
            "bu_id":     bu_id,
            "group":     group_id,
            "label":     attrs.get("label", base),
            "gn":        GROUP_NAMES.get(group_id, f"Gruppe {group_id}"),
            "s":   sensor_id,
            "sel": find_entity("select", "status_setzen"),
            "sw":  find_entity("switch", "einsatzreservierung"),
            "tl":  find_entity("text",   "bezeichnung"),
            "tn":  find_entity("text",   "name"),
            "tr":  find_entity("text",   "funkrufname"),
            "tc":  find_entity("text",   "kommentar"),
            "tka": find_entity("text",   "kategorie"),
            "ti":  find_entity("text",   "issi"),
        })

    assets.sort(key=lambda a: (a["group"], a.get("label", "")))
    return assets


def find_reports(states):
    """Find all STEIN report sensor entities."""
    reports = []
    for state in states:
        eid = state["entity_id"]
        attrs = state.get("attributes", {})
        # Report sensors: sensor.stein_report_{id}
        if (eid.startswith("sensor.stein_report_") and
                "einsatz_stichwort" in attrs):
            reports.append({
                "entity_id": eid,
                "state":     state.get("state", ""),
                "attrs":     attrs,
                "report_id": attrs.get("id"),
                "finished":  attrs.get("finished", False),
                "stichwort": attrs.get("einsatz_stichwort") or "–",
                "schadenort": attrs.get("schadenort") or "–",
                "einsatzbeginn": attrs.get("einsatzbeginn"),
                "asset_names": attrs.get("asset_names", []),
                "ek_gesamt": attrs.get("anzahl_ek_gesamt", 0),
                "meldeschwellen": attrs.get("meldeschwellen", []),
                "bu_name":   attrs.get("bu_name") or "–",
            })
    # Active first, then finished; within each group by einsatzbeginn desc
    reports.sort(key=lambda r: (r["finished"], -(
        0 if not r["einsatzbeginn"] else
        int(r["einsatzbeginn"].replace("Z","").replace("T","").replace("-","").replace(":","").replace(" ","")[:14])
    )))
    return reports


def find_bu_sensor(states, bu_id):
    for state in states:
        eid = state["entity_id"]
        attrs = state.get("attributes", {})
        if (eid.startswith("sensor.") and
                attrs.get("id") == bu_id and
                "stats_ready" in attrs):
            return eid
    return f"sensor.stein_bu_{bu_id}"


def find_einsatz_binary_sensor(states, bu_id):
    candidate = f"binary_sensor.stein_bu_{bu_id}_einsatz_aktiv"
    for state in states:
        if state["entity_id"] == candidate:
            return candidate
    return candidate


def find_aktive_einsaetze_sensor(states, bu_id):
    candidate = f"sensor.stein_bu_{bu_id}_aktive_einsaetze"
    for state in states:
        if state["entity_id"] == candidate:
            return candidate
    return candidate


# ── Template-Helfer ───────────────────────────────────────────────────────────

def icon_j(s):
    return (f"{{% set st=state_attr('{s}','status_raw') %}}"
            f"{{% if st=='ready' %}}mdi:check-circle"
            f"{{% elif st=='notready' %}}mdi:close-circle"
            f"{{% elif st=='semiready' %}}mdi:alert-circle"
            f"{{% elif st=='inuse' %}}mdi:fire-truck"
            f"{{% elif st=='maint' %}}mdi:wrench"
            f"{{% else %}}mdi:help-circle{{% endif %}}")


def color_j(s):
    return (f"{{% set st=state_attr('{s}','status_raw') %}}"
            f"{{% if st=='ready' %}}green"
            f"{{% elif st=='notready' %}}red"
            f"{{% elif st=='semiready' %}}orange"
            f"{{% elif st=='inuse' %}}blue"
            f"{{% elif st=='maint' %}}purple"
            f"{{% else %}}grey{{% endif %}}")


def show_asset(s, gn):
    f = FILTER_ENTITY
    return (
        f"states('{f}') in ['Alle','{gn}'] or "
        f"(states('{f}')=='Probleme' and state_attr('{s}','status_raw') not in ['ready']) or "
        f"(states('{f}')=='Bereit' and state_attr('{s}','status_raw')=='ready') or "
        f"(states('{f}')=='Bedingt' and state_attr('{s}','status_raw')=='semiready') or "
        f"(states('{f}')=='Nicht bereit' and state_attr('{s}','status_raw')=='notready') or "
        f"(states('{f}')=='Im Einsatz' and state_attr('{s}','status_raw')=='inuse') or "
        f"(states('{f}')=='Wartung' and state_attr('{s}','status_raw')=='maint')"
    )


def show_group(gassets, gn):
    f = FILTER_ENTITY
    prob = " or ".join([
        f"state_attr('{a['s']}','status_raw') not in ['ready']"
        for a in gassets
    ])
    return (
        f"states('{f}') in ['Alle','{gn}'] or "
        f"(states('{f}') in ['Probleme','Bereit','Bedingt','Nicht bereit','Im Einsatz','Wartung'] "
        f"and ({prob}))"
    )


def count_j(status, assets):
    parts = [
        f"(1 if state_attr('{a['s']}','status_raw')=='{status}' else 0)"
        for a in assets
    ]
    return "{{ " + " + ".join(parts) + " }}"


# ── Popup Builder (Assets) ────────────────────────────────────────────────────

def popup(a):
    s = a["s"]
    return {
        "type": "vertical-stack",
        "cards": [
            {
                "type": "custom:mushroom-template-card",
                "primary": (
                    f"{{{{ state_attr('{s}','label') | default('{a['label']}') }}}}"
                    f"{{%- if state_attr('{s}','name') %}} · {{{{ state_attr('{s}','name') }}}}{{%- endif %}}"
                ),
                "secondary": (
                    f"{{% set ts=state_attr('{s}','last_modified') %}}"
                    f"{{% set by=state_attr('{s}','last_modified_by') %}}"
                    f"{{% if by and ts %}}Zuletzt von {{{{ by }}}} am "
                    f"{{{{ as_timestamp(ts)|timestamp_custom('%d. %b %Y %H:%M') }}}}{{% endif %}}"
                ),
                "icon":       icon_j(s),
                "icon_color": color_j(s),
            },
            {
                "type": "entities",
                "title": "Status",
                "show_header_toggle": False,
                "entities": [
                    {"entity": a["sel"], "name": "Status"},
                    {"entity": a["sw"],  "name": "Einsatzreservierung"},
                ]
            },
            {
                "type": "entities",
                "title": "Felder bearbeiten",
                "show_header_toggle": False,
                "entities": [
                    {"entity": a["tl"],  "name": "Bezeichnung"},
                    {"entity": a["tn"],  "name": "Name / Kennzeichen"},
                    {"entity": a["tr"],  "name": "Funkrufname"},
                    {"entity": a["tc"],  "name": "Kommentar"},
                    {"entity": a["tka"], "name": "Kategorie"},
                    {"entity": a["ti"],  "name": "ISSI"},
                ]
            },
            {
                "type": "markdown",
                "content": (
                    f"**Kommentar**\n\n"
                    f"{{{{ state_attr('{s}','comment') | default('–') | replace('\\\\n','\\n') }}}}"
                ),
            },
            {
                "type": "entities",
                "title": "Details",
                "show_header_toggle": False,
                "entities": [
                    {"type":"attribute","entity":s,"attribute":"radio_name",      "name":"Funkrufname",   "icon":"mdi:radio"},
                    {"type":"attribute","entity":s,"attribute":"issi",            "name":"ISSI",          "icon":"mdi:signal"},
                    {"type":"attribute","entity":s,"attribute":"hu_valid_until",  "name":"HU gueltig bis","icon":"mdi:calendar-check"},
                    {"type":"attribute","entity":s,"attribute":"group_id",        "name":"Gruppe",        "icon":"mdi:folder"},
                    {"type":"attribute","entity":s,"attribute":"id",              "name":"Asset-ID",      "icon":"mdi:identifier"},
                    {"type":"attribute","entity":s,"attribute":"last_modified_by","name":"Geaendert von", "icon":"mdi:account-edit"},
                    {"type":"attribute","entity":s,"attribute":"last_modified",   "name":"Geaendert am",  "icon":"mdi:clock-edit"},
                ]
            }
        ]
    }


# ── Report Popup Builder ──────────────────────────────────────────────────────

def report_popup(r):
    e = r["entity_id"]
    rid = r["report_id"]
    return {
        "type": "vertical-stack",
        "cards": [
            # Header
            {
                "type": "custom:mushroom-template-card",
                "primary": (
                    f"{{{{ state_attr('{e}','einsatz_stichwort') | default('Einsatz #{rid}') }}}}"
                ),
                "secondary": (
                    f"{{{{ state_attr('{e}','schadenort') | default('Schadenort unbekannt') }}}}"
                    f"{{%- if state_attr('{e}','zip_code') %}} · PLZ {{{{ state_attr('{e}','zip_code') }}}}{{%- endif %}}"
                ),
                "icon": "mdi:clipboard-alert",
                "icon_color": (
                    f"{{% if states('{e}')=='Abgeschlossen' %}}grey"
                    f"{{% else %}}red{{% endif %}}"
                ),
            },
            # Einsatz-Kerndaten
            {
                "type": "entities",
                "title": "Einsatz",
                "show_header_toggle": False,
                "entities": [
                    {"type":"attribute","entity":e,"attribute":"einsatz_stichwort",    "name":"Stichwort",       "icon":"mdi:alert"},
                    {"type":"attribute","entity":e,"attribute":"schadenort",           "name":"Schadenort",      "icon":"mdi:map-marker"},
                    {"type":"attribute","entity":e,"attribute":"zip_code",             "name":"PLZ",             "icon":"mdi:mailbox"},
                    {"type":"attribute","entity":e,"attribute":"schaden",              "name":"Schaden",         "icon":"mdi:home-alert"},
                    {"type":"attribute","entity":e,"attribute":"art_tech_unterstuetzung","name":"Art",           "icon":"mdi:tag"},
                    {"type":"attribute","entity":e,"attribute":"einsatzbeginn",        "name":"Beginn",          "icon":"mdi:clock-start"},
                    {"type":"attribute","entity":e,"attribute":"einsatzende",          "name":"Ende",            "icon":"mdi:clock-end"},
                    {"type":"attribute","entity":e,"attribute":"vor_einsatzende_hours","name":"Voraus. Ende",    "icon":"mdi:timer"},
                    {"type":"attribute","entity":e,"attribute":"auftragsnummer",       "name":"Auftragsnr.",     "icon":"mdi:file-document"},
                    {"type":"attribute","entity":e,"attribute":"dienststelle",         "name":"Dienststelle",    "icon":"mdi:office-building"},
                    {"type":"attribute","entity":e,"attribute":"meldeschwellen",       "name":"Meldeschwellen",  "icon":"mdi:chart-line"},
                    {"type":"attribute","entity":e,"attribute":"finished",             "name":"Abgeschlossen",   "icon":"mdi:check"},
                ]
            },
            # Fahrzeuge
            {
                "type": "custom:mushroom-template-card",
                "primary": "Beteiligte Fahrzeuge",
                "secondary": (
                    f"{{% set names = state_attr('{e}','asset_names') %}}"
                    f"{{% if names and names|length > 0 %}}"
                    f"{{{{ names | join(' · ') }}}}"
                    f"{{% else %}}–{{% endif %}}"
                ),
                "icon": "mdi:fire-truck",
                "icon_color": "blue",
            },
            # Einsatzkräfte
            {
                "type": "entities",
                "title": "Einsatzkräfte",
                "show_header_toggle": False,
                "entities": [
                    {"type":"attribute","entity":e,"attribute":"anzahl_ek1",      "name":"EK1",         "icon":"mdi:account"},
                    {"type":"attribute","entity":e,"attribute":"anzahl_ek2",      "name":"EK2",         "icon":"mdi:account"},
                    {"type":"attribute","entity":e,"attribute":"anzahl_ek3",      "name":"EK3",         "icon":"mdi:account"},
                    {"type":"attribute","entity":e,"attribute":"anzahl_ek_gesamt","name":"Gesamt EK",   "icon":"mdi:account-group"},
                ]
            },
            # Betroffene
            {
                "type": "entities",
                "title": "Betroffene Personen",
                "show_header_toggle": False,
                "entities": [
                    {"type":"attribute","entity":e,"attribute":"betroffene_unverletzte","name":"Unverletzt",  "icon":"mdi:account-check"},
                    {"type":"attribute","entity":e,"attribute":"betroffene_verletzte",  "name":"Verletzt",    "icon":"mdi:bandage"},
                    {"type":"attribute","entity":e,"attribute":"betroffene_tote",       "name":"Tote",        "icon":"mdi:account-off"},
                    {"type":"attribute","entity":e,"attribute":"betroffene_vermisste",  "name":"Vermisste",   "icon":"mdi:account-question"},
                ]
            },
            # Besonderheiten
            {
                "type": "markdown",
                "content": (
                    f"**Besonderheiten**\n\n"
                    f"{{{{ state_attr('{e}','besonderheiten') | default('–') }}}}"
                ),
            },
            # Metadaten
            {
                "type": "entities",
                "title": "Metadaten",
                "show_header_toggle": False,
                "entities": [
                    {"type":"attribute","entity":e,"attribute":"author",           "name":"Ersteller",    "icon":"mdi:account"},
                    {"type":"attribute","entity":e,"attribute":"author_phone",     "name":"Telefon",      "icon":"mdi:phone"},
                    {"type":"attribute","entity":e,"attribute":"bu_name",          "name":"OV",           "icon":"mdi:home-group"},
                    {"type":"attribute","entity":e,"attribute":"last_modified_by", "name":"Geändert von", "icon":"mdi:account-edit"},
                    {"type":"attribute","entity":e,"attribute":"last_modified",    "name":"Geändert am",  "icon":"mdi:clock-edit"},
                    {"type":"attribute","entity":e,"attribute":"id",               "name":"Einsatz-ID",   "icon":"mdi:identifier"},
                ]
            },
        ]
    }


# ── Assets View Builder ───────────────────────────────────────────────────────

def build_assets_view(assets, states):
    groups = {}
    for a in assets:
        groups.setdefault(a["group"], []).append(a)

    bu_ids = sorted(set(a["bu_id"] for a in assets if a["bu_id"]))
    cards = []

    # BU Info Karten
    for bu_id in bu_ids:
        BU = find_bu_sensor(states, bu_id)
        cards.append({
            "type": "custom:mushroom-template-card",
            "primary": (
                f"{{{{ state_attr('{BU}','name') | default('THW OV {bu_id}') }}}}"
                f" ({{{{ state_attr('{BU}','code') | default('') }}}})"
            ),
            "secondary": (
                f"{{% set bu='{BU}' %}}"
                f"{{% set r=state_attr(bu,'stats_ready') | int(0) if states(bu) not in ['unavailable','unknown'] else 0 %}}"
                f"{{% set p=state_attr(bu,'readiness_pct') | int(0) if states(bu) not in ['unavailable','unknown'] else 0 %}}"
                f"{{{{ r }}}} Einsatzbereit · {{{{ p }}}}%"
                f" · {{{{ state_attr('{VERBINDUNG}','email') | default('') }}}}"
            ),
            "icon": "mdi:home-group",
            "icon_color": (
                f"{{% set bu='{BU}' %}}"
                f"{{% set p=state_attr(bu,'readiness_pct') | int(0) if states(bu) not in ['unavailable','unknown'] else 0 %}}"
                f"{{% if p>=75 %}}green{{% elif p>=50 %}}orange{{% else %}}red{{% endif %}}"
            ),
            "tap_action": {
                "action": "fire-dom-event",
                "browser_mod": {
                    "service": "browser_mod.popup",
                    "data": {
                        "title": "Ortsverband & API",
                        "content": {
                            "type": "vertical-stack",
                            "cards": [
                                {
                                    "type": "entities",
                                    "title": "Ortsverband",
                                    "show_header_toggle": False,
                                    "entities": [
                                        {"type":"attribute","entity":BU,"attribute":"name",           "name":"Name",            "icon":"mdi:home-group"},
                                        {"type":"attribute","entity":BU,"attribute":"code",           "name":"Kuerzel",          "icon":"mdi:identifier"},
                                        {"type":"attribute","entity":BU,"attribute":"id",             "name":"ID",               "icon":"mdi:numeric"},
                                        {"type":"attribute","entity":BU,"attribute":"region_id",      "name":"Region-ID",        "icon":"mdi:map-marker"},
                                        {"type":"attribute","entity":BU,"attribute":"author",         "name":"Erstellt von",     "icon":"mdi:account"},
                                        {"type":"attribute","entity":BU,"attribute":"last_modified",  "name":"Letzte Aenderung", "icon":"mdi:clock-edit"},
                                        {"type":"attribute","entity":BU,"attribute":"stats_ready",    "name":"Einsatzbereit",    "icon":"mdi:check-circle"},
                                        {"type":"attribute","entity":BU,"attribute":"stats_notready", "name":"Nicht bereit",     "icon":"mdi:close-circle"},
                                        {"type":"attribute","entity":BU,"attribute":"stats_semiready","name":"Bedingt",          "icon":"mdi:alert-circle"},
                                        {"type":"attribute","entity":BU,"attribute":"stats_inuse",    "name":"Im Einsatz",       "icon":"mdi:fire-truck"},
                                        {"type":"attribute","entity":BU,"attribute":"stats_maint",    "name":"In Wartung",       "icon":"mdi:wrench"},
                                        {"type":"attribute","entity":BU,"attribute":"readiness_pct",  "name":"Einsatzbereit %",  "icon":"mdi:chart-bar"},
                                    ]
                                },
                                {
                                    "type": "markdown",
                                    "content": f"**Kommentar / Kontakt**\n\n{{{{ state_attr('{BU}','comment') | default('–') | replace('\\\\n','\\n') }}}}",
                                },
                                {
                                    "type": "entities",
                                    "title": "API Verbindung",
                                    "show_header_toggle": False,
                                    "entities": [
                                        {"entity": VERBINDUNG, "name": "Nutzer"},
                                        {"type":"attribute","entity":VERBINDUNG,"attribute":"email",                "name":"E-Mail",          "icon":"mdi:email"},
                                        {"type":"attribute","entity":VERBINDUNG,"attribute":"scope",                "name":"Zugriffsbereich", "icon":"mdi:shield-account"},
                                        {"type":"attribute","entity":VERBINDUNG,"attribute":"scope_role_permission","name":"Berechtigung",    "icon":"mdi:key"},
                                    ]
                                },
                            ]
                        }
                    }
                }
            }
        })

    # Statuskacheln
    kacheln = []
    for raw, label, icon, color in STATUS_FILTERS:
        kacheln.append({
            "type": "custom:mushroom-template-card",
            "primary": count_j(raw, assets),
            "secondary": label,
            "icon": icon,
            "icon_color": color,
            "layout": "vertical",
            "tap_action": {
                "action": "call-service",
                "service": "input_select.select_option",
                "service_data": {"entity_id": FILTER_ENTITY, "option": label}
            }
        })
    cards.append({"type": "horizontal-stack", "cards": kacheln})

    # Filter Chips
    chips = []
    chip_defs = [("Alle", "mdi:format-list-bulleted", "grey")]
    for gid in sorted(groups.keys()):
        gn = GROUP_NAMES.get(gid, f"Gruppe {gid}")
        icon_map = {
            "Fahrzeuge":        ("mdi:fire-truck",    "blue"),
            "Geraete":          ("mdi:tools",         "brown"),
            "Sonderfunktionen": ("mdi:star",          "teal"),
            "Einheiten":        ("mdi:account-group", "purple"),
            "Anhaenger":        ("mdi:truck-trailer", "orange"),
        }
        icon, color = icon_map.get(gn, ("mdi:folder", "grey"))
        chip_defs.append((gn, icon, color))
    chip_defs.append(("Probleme", "mdi:alert", "red"))

    for opt, icon, color in chip_defs:
        chips.append({
            "type": "template",
            "content": opt,
            "icon": icon,
            "icon_color": f"{{% if states('{FILTER_ENTITY}')=='{opt}' %}}{color}{{% else %}}grey{{% endif %}}",
            "tap_action": {
                "action": "call-service",
                "service": "input_select.select_option",
                "service_data": {"entity_id": FILTER_ENTITY, "option": opt}
            }
        })
    cards.append({"type": "custom:mushroom-chips-card", "chips": chips})

    # Dashboard-Rebuild Button
    cards.append({
        "type": "custom:mushroom-template-card",
        "primary": "Dashboard aktualisieren",
        "secondary": "Neu generieren wenn Assets hinzugekommen sind",
        "icon": "mdi:refresh",
        "icon_color": "blue",
        "tap_action": {
            "action": "call-service",
            "service": "shell_command.stein_dashboard_rebuild",
        }
    })

    # Gruppen + Assets – jede Gruppe als vertical-stack Card
    for gid in sorted(groups.keys()):
        gname = GROUP_NAMES.get(gid, f"Gruppe {gid}")
        gassets = groups[gid]

        group_icon_map = {
            "Fahrzeuge":        "mdi:fire-truck",
            "Geraete":          "mdi:tools",
            "Sonderfunktionen": "mdi:star",
            "Einheiten":        "mdi:account-group",
            "Anhaenger":        "mdi:truck-trailer",
        }
        group_icon = group_icon_map.get(gname, "mdi:folder")

        asset_cards = []
        for a in gassets:
            s = a["s"]
            gn = a["gn"]
            asset_cards.append({
                "type": "custom:mushroom-template-card",
                "entity": s,
                "primary": (
                    f"{{{{ state_attr('{s}','label') | default('{a['label']}') }}}}"
                    f"{{%- if state_attr('{s}','radio_name') %}} · {{{{ state_attr('{s}','radio_name') }}}}{{%- endif %}}"
                    f"{{%- if state_attr('{s}','name') %}} · {{{{ state_attr('{s}','name') }}}}{{%- endif %}}"
                ),
                "secondary": (
                    f"{{{{ states('{s}') }}}}"
                    f"{{%- if state_attr('{s}','comment') and state_attr('{s}','comment')|trim|length > 0 %}}"
                    f" · {{{{ state_attr('{s}','comment') }}}}{{%- endif %}}"
                ),
                "icon":       icon_j(s),
                "icon_color": color_j(s),
                "badge_icon": f"{{% if state_attr('{s}','operation_reservation') %}}mdi:bookmark-check{{% endif %}}",
                "badge_color": "blue",
                "tap_action": {
                    "action": "fire-dom-event",
                    "browser_mod": {
                        "service": "browser_mod.popup",
                        "data": {"title": a["label"], "content": popup(a)}
                    }
                },
                "card_mod": {
                    "style": f":host {{ display: {{{{ 'block' if {show_asset(s, gn)} else 'none' }}}}; }}"
                }
            })

        # Gruppe als vertical-stack: Titel + alle Asset-Karten in einer Box
        cards.append({
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "custom:mushroom-title-card",
                    "title": gname,
                    "icon": group_icon,
                },
                *asset_cards,
            ],
            "card_mod": {
                "style": f":host {{ display: {{{{ 'block' if {show_group(gassets, gname)} else 'none' }}}}; }}"
            }
        })

    return {
        "title": "Assets",
        "path": "stein-assets",
        "icon": "mdi:fire-truck",
        "max_columns": 1,
        "cards": cards,
    }


# ── Einsatz View Builder ──────────────────────────────────────────────────────

def build_einsaetze_view(reports, states, bu_ids_list):
    cards = []

    # Header – Einsatz-Status pro BU
    for bu_id in bu_ids_list:
        binary = find_einsatz_binary_sensor(states, bu_id)
        summary = find_aktive_einsaetze_sensor(states, bu_id)
        bu_sensor = find_bu_sensor(states, bu_id)

        cards.append({
            "type": "custom:mushroom-template-card",
            "primary": (
                f"{{{{ state_attr('{bu_sensor}','name') | default('OV {bu_id}') }}}}"
            ),
            "secondary": (
                f"{{% set n=states('{summary}') | int(0) %}}"
                f"{{% if n > 0 %}}"
                f"🚨 {{{{ n }}}} aktiver Einsatz{{{{ 'ätze' if n > 1 else '' }}}}"
                f"{{% else %}}Kein aktiver Einsatz{{% endif %}}"
            ),
            "icon": "mdi:alarm-light",
            "icon_color": (
                f"{{% if is_state('{binary}','on') %}}red{{% else %}}green{{% endif %}}"
            ),
            "badge_icon": (
                f"{{% if is_state('{binary}','on') %}}mdi:alert{{% endif %}}"
            ),
            "badge_color": "red",
        })

    # Aktive Einsätze Sektion
    active_reports = [r for r in reports if not r["finished"]]
    finished_reports = [r for r in reports if r["finished"]]

    if active_reports:
        cards.append({
            "type": "custom:mushroom-title-card",
            "title": f"🚨 Aktive Einsätze ({len(active_reports)})",
        })

        for r in active_reports:
            e = r["entity_id"]
            asset_names = r["asset_names"]
            asset_str = " · ".join(asset_names[:3]) if asset_names else "–"
            if len(asset_names) > 3:
                asset_str += f" (+{len(asset_names)-3})"

            schwellen = r["meldeschwellen"]
            schwellen_str = " · ".join([f"MS{s}" for s in schwellen]) if schwellen else ""

            cards.append({
                "type": "custom:mushroom-template-card",
                "entity": e,
                "primary": (
                    f"{{{{ state_attr('{e}','einsatz_stichwort') | default('Einsatz') }}}}"
                    f"{{%- if state_attr('{e}','meldeschwellen') and state_attr('{e}','meldeschwellen')|length > 0 %}}"
                    f" · MS{{{{ state_attr('{e}','meldeschwellen') | join('/') }}}}"
                    f"{{%- endif %}}"
                ),
                "secondary": (
                    f"📍 {{{{ state_attr('{e}','schadenort') | default('–') }}}}"
                    f"{{% if state_attr('{e}','einsatzbeginn') %}}"
                    f" · {{{{ as_timestamp(state_attr('{e}','einsatzbeginn'))|timestamp_custom('%d.%m. %H:%M') }}}}"
                    f"{{% endif %}}"
                    f"{{% set names=state_attr('{e}','asset_names') %}}"
                    f"{{% if names and names|length > 0 %}}"
                    f"\\n🚒 {{{{ names | join(' · ') }}}}"
                    f"{{% endif %}}"
                ),
                "icon": "mdi:clipboard-alert",
                "icon_color": "red",
                "badge_icon": (
                    f"{{% set ek=state_attr('{e}','anzahl_ek_gesamt') | int(0) %}}"
                    f"{{% if ek > 0 %}}mdi:account-group{{% endif %}}"
                ),
                "badge_color": "orange",
                "tap_action": {
                    "action": "fire-dom-event",
                    "browser_mod": {
                        "service": "browser_mod.popup",
                        "data": {
                            "title": f"Einsatz #{r['report_id']}",
                            "content": report_popup(r),
                        }
                    }
                },
            })
    else:
        cards.append({
            "type": "custom:mushroom-template-card",
            "primary": "Keine aktiven Einsätze",
            "secondary": "Alle Einsätze abgeschlossen",
            "icon": "mdi:check-circle",
            "icon_color": "green",
        })

    # Abgeschlossene Einsätze (letzte 10)
    if finished_reports:
        recent_finished = finished_reports[:10]
        cards.append({
            "type": "custom:mushroom-title-card",
            "title": f"Abgeschlossene Einsätze (letzte {len(recent_finished)})",
        })

        for r in recent_finished:
            e = r["entity_id"]
            cards.append({
                "type": "custom:mushroom-template-card",
                "entity": e,
                "primary": (
                    f"{{{{ state_attr('{e}','einsatz_stichwort') | default('Einsatz') }}}}"
                ),
                "secondary": (
                    f"📍 {{{{ state_attr('{e}','schadenort') | default('–') }}}}"
                    f"{{% if state_attr('{e}','einsatzbeginn') %}}"
                    f" · {{{{ as_timestamp(state_attr('{e}','einsatzbeginn'))|timestamp_custom('%d.%m.%Y') }}}}"
                    f"{{% endif %}}"
                ),
                "icon": "mdi:clipboard-check",
                "icon_color": "grey",
                "tap_action": {
                    "action": "fire-dom-event",
                    "browser_mod": {
                        "service": "browser_mod.popup",
                        "data": {
                            "title": f"Einsatz #{r['report_id']}",
                            "content": report_popup(r),
                        }
                    }
                },
            })

    return {
        "title": "Einsätze",
        "path": "stein-einsaetze",
        "icon": "mdi:clipboard-alert",
        "max_columns": 1,
        "cards": cards,
    }


# ── Dashboard Builder ─────────────────────────────────────────────────────────

def build_dashboard(assets, reports, states):
    bu_ids_list = sorted(set(a["bu_id"] for a in assets if a["bu_id"]))

    assets_view = build_assets_view(assets, states)
    einsaetze_view = build_einsaetze_view(reports, states, bu_ids_list)

    return {
        "title": "STEIN",
        "views": [assets_view, einsaetze_view],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = get_token()
    if not token:
        print("FEHLER: Kein Token. Bitte in /config/scripts/stein_token.txt ablegen.")
        sys.exit(1)

    print("Lade States von Home Assistant...")
    try:
        states = ha_get_states(token)
    except urllib.error.URLError as e:
        print(f"FEHLER: Kann HA nicht erreichen: {e}")
        sys.exit(1)

    assets = find_assets(states)
    print(f"\nGefundene Assets: {len(assets)}")
    for a in assets:
        print(f"  [{a['group']}] {a['label']:40s} → {a['s']}")

    if not assets:
        print("\nFEHLER: Keine STEIN-Assets gefunden.")
        sys.exit(1)

    reports = find_reports(states)
    active_count = sum(1 for r in reports if not r["finished"])
    print(f"\nGefundene Einsätze: {len(reports)} ({active_count} aktiv)")
    for r in reports:
        status = "✅ abgeschlossen" if r["finished"] else "🚨 aktiv"
        print(f"  [{status}] #{r['report_id']} {r['stichwort']} – {r['schadenort']}")

    dashboard = build_dashboard(assets, reports, states)

    os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
    output = yaml.dump(
        dashboard, allow_unicode=True, sort_keys=False,
        default_flow_style=False, width=200000
    )

    with open(DASHBOARD_FILE, "w") as f:
        f.write(output)

    total_cards = sum(len(v["cards"]) for v in dashboard["views"])
    print(f"\nDashboard gespeichert: {DASHBOARD_FILE}")
    print(f"Views: {len(dashboard['views'])} | Karten gesamt: {total_cards}")
    print("Bitte Browser-Seite neu laden (F5).")


if __name__ == "__main__":
    main()
