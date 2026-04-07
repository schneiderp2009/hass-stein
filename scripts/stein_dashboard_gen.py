#!/usr/bin/env python3
"""
STEIN Dashboard Generator
Liest alle STEIN-Assets aus dem HA State Machine via REST API
und generiert eine vollstaendige dashboard.yaml.

Aufruf: python3 /config/scripts/stein_dashboard_gen.py
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
import yaml

# ── Konfiguration ────────────────────────────────────────────────────────────
HA_URL    = "http://localhost:8123"
TOKEN_FILE = "/config/scripts/stein_token.txt"   # Long-Lived Access Token
DASHBOARD_FILE = "/config/dashboards/stein.yaml" # Ausgabedatei
BU_SENSOR = "sensor.schwabisch_gmund_fahrzeuge_gesamt"
VERBINDUNG = "sensor.stein_api_stein_verbindung"
FILTER_ENTITY = "input_select.stein_filter"

GROUP_NAMES = {
    1: "Fahrzeuge",
    2: "Geraete",
    3: "Sonderfunktionen",
    4: "Einheiten",
    5: "Anhaenger",
}

STATUS_FILTERS = [
    ("ready",    "Bereit",       "mdi:check-circle", "green"),
    ("semiready","Bedingt",      "mdi:alert-circle", "orange"),
    ("notready", "Nicht bereit", "mdi:close-circle", "red"),
    ("inuse",    "Im Einsatz",   "mdi:fire-truck",   "blue"),
    ("maint",    "Wartung",      "mdi:wrench",       "purple"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def slug(name):
    s = name.lower()
    for a, b in [("ä","a"),("ö","o"),("ü","u"),("ß","ss"),(",",""),("-","_")]:
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def get_token():
    if os.path.exists(TOKEN_FILE):
        return open(TOKEN_FILE).read().strip()
    # Fallback: Umgebungsvariable
    return os.environ.get("SUPERVISOR_TOKEN", "")


def ha_get_states(token):
    req = urllib.request.Request(
        f"{HA_URL}/api/states",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def find_assets(states):
    """Alle STEIN Asset-Sensoren finden und nach Gruppe sortieren."""
    assets = []
    for state in states:
        entity_id = state["entity_id"]
        attrs = state.get("attributes", {})
        if (entity_id.startswith("sensor.") and
                entity_id.endswith("_status") and
                "status_raw" in attrs and
                "bu_id" in attrs):
            sl = entity_id.replace("sensor.", "").replace("_status", "")
            assets.append({
                "entity_id": entity_id,
                "slug": sl,
                "label": attrs.get("label", sl),
                "group": attrs.get("group_id", 99),
                "bu_id": attrs.get("bu_id"),
                "s":   entity_id,
                "sel": f"select.{sl}_status_setzen",
                "sw":  f"switch.{sl}_einsatzreservierung",
                "tl":  f"text.{sl}_bezeichnung",
                "tn":  f"text.{sl}_name",
                "tr":  f"text.{sl}_funkrufname",
                "tc":  f"text.{sl}_kommentar",
                "tka": f"text.{sl}_kategorie",
                "ti":  f"text.{sl}_issi",
                "gn":  GROUP_NAMES.get(attrs.get("group_id", 99), f"Gruppe {attrs.get('group_id', 99)}"),
            })
    assets.sort(key=lambda a: (a["group"], a["label"]))
    return assets


# ── Template-Helfer ────────────────────────────────────────────────────────────

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
    prob = " or ".join([f"state_attr('{a['s']}','status_raw') not in ['ready']" for a in gassets])
    return (
        f"states('{f}') in ['Alle','{gn}'] or "
        f"(states('{f}') in ['Probleme','Bereit','Bedingt','Nicht bereit','Im Einsatz','Wartung'] "
        f"and ({prob}))"
    )


def count_j(status, assets):
    parts = [f"(1 if state_attr('{a['s']}','status_raw')=='{status}' else 0)" for a in assets]
    return "{{ " + " + ".join(parts) + " }}"


# ── Popup Builder ──────────────────────────────────────────────────────────────

def popup(a):
    s = a["s"]
    return {
        "type": "vertical-stack",
        "cards": [
            {
                "type": "custom:mushroom-template-card",
                "primary": (f"{{{{ state_attr('{s}','label') | default('{a['label']}') }}}}"
                            f"{{%- if state_attr('{s}','name') %}} · {{{{ state_attr('{s}','name') }}}}{{%- endif %}}"),
                "secondary": (f"{{% set ts=state_attr('{s}','last_modified') %}}"
                              f"{{% set by=state_attr('{s}','last_modified_by') %}}"
                              f"{{% if by and ts %}}Zuletzt von {{{{ by }}}} am "
                              f"{{{{ as_timestamp(ts)|timestamp_custom('%d. %b %Y %H:%M') }}}}{{% endif %}}"),
                "icon": icon_j(s),
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
                "content": (f"**Kommentar**\n\n"
                            f"{{{{ state_attr('{s}','comment') | default('–') | replace('\\\\n','\\n') }}}}"),
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


# ── Dashboard Builder ─────────────────────────────────────────────────────────

def build_dashboard(assets):
    groups = {}
    for a in assets:
        groups.setdefault(a["group"], []).append(a)

    cards = []

    # BU Info
    cards.append({
        "type": "custom:mushroom-template-card",
        "primary": (f"{{{{ state_attr('{BU_SENSOR}','name') | default('THW OV') }}}}"
                    f" ({{{{ state_attr('{BU_SENSOR}','code') | default('') }}}})"),
        "secondary": (f"{{% set r=state_attr('{BU_SENSOR}','stats_ready')|default(0)|int %}}"
                      f"{{% set p=state_attr('{BU_SENSOR}','readiness_pct')|default(0)|int %}}"
                      f"{{{{ r }}}} Einsatzbereit · {{{{ p }}}}%"
                      f" · {{{{ state_attr('{VERBINDUNG}','email')|default('') }}}}"),
        "icon": "mdi:home-group",
        "icon_color": (f"{{% set p=state_attr('{BU_SENSOR}','readiness_pct')|default(0)|int %}}"
                       f"{{% if p>=75 %}}green{{% elif p>=50 %}}orange{{% else %}}red{{% endif %}}"),
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
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"name",         "name":"Name",           "icon":"mdi:home-group"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"code",         "name":"Kuerzel",         "icon":"mdi:identifier"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"id",           "name":"ID",              "icon":"mdi:numeric"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"region_id",    "name":"Region-ID",       "icon":"mdi:map-marker"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"author",       "name":"Erstellt von",    "icon":"mdi:account"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"last_modified","name":"Letzte Aenderung","icon":"mdi:clock-edit"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"stats_ready",  "name":"Einsatzbereit",   "icon":"mdi:check-circle"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"stats_notready","name":"Nicht bereit",   "icon":"mdi:close-circle"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"stats_semiready","name":"Bedingt",       "icon":"mdi:alert-circle"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"stats_inuse",  "name":"Im Einsatz",      "icon":"mdi:fire-truck"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"stats_maint",  "name":"In Wartung",      "icon":"mdi:wrench"},
                                    {"type":"attribute","entity":BU_SENSOR,"attribute":"readiness_pct","name":"Einsatzbereit %", "icon":"mdi:chart-bar"},
                                ]
                            },
                            {
                                "type": "markdown",
                                "content": f"**Kommentar / Kontakt**\n\n{{{{ state_attr('{BU_SENSOR}','comment') | default('–') | replace('\\\\n','\\n') }}}}",
                            },
                            {
                                "type": "entities",
                                "title": "API Verbindung",
                                "show_header_toggle": False,
                                "entities": [
                                    {"entity": VERBINDUNG, "name": "Nutzer"},
                                    {"type":"attribute","entity":VERBINDUNG,"attribute":"email",                "name":"E-Mail",         "icon":"mdi:email"},
                                    {"type":"attribute","entity":VERBINDUNG,"attribute":"scope",                "name":"Zugriffsbereich","icon":"mdi:shield-account"},
                                    {"type":"attribute","entity":VERBINDUNG,"attribute":"scope_role_permission","name":"Berechtigung",   "icon":"mdi:key"},
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
            "tap_action": {"action":"call-service","service":"input_select.select_option",
                           "service_data":{"entity_id":FILTER_ENTITY,"option":label}}
        })
    cards.append({"type":"horizontal-stack","cards":kacheln})

    # Chips
    chips = []
    chip_defs = [("Alle","mdi:format-list-bulleted","grey")] + [
        (gn, icon, color) for gn, icon, color in [
            ("Fahrzeuge",      "mdi:fire-truck",   "blue"),
            ("Geraete",        "mdi:tools",        "brown"),
            ("Sonderfunktionen","mdi:star",         "teal"),
            ("Einheiten",      "mdi:account-group","purple"),
            ("Anhaenger",      "mdi:truck-trailer","orange"),
            ("Probleme",       "mdi:alert",        "red"),
        ]
    ]
    # Add any unknown groups dynamically
    for gid in sorted(groups.keys()):
        if gid not in GROUP_NAMES:
            chip_defs.append((f"Gruppe {gid}", "mdi:folder", "grey"))

    for opt, icon, color in chip_defs:
        chips.append({
            "type":"template","content":opt,"icon":icon,
            "icon_color": f"{{% if states('{FILTER_ENTITY}')=='{opt}' %}}{color}{{% else %}}grey{{% endif %}}",
            "tap_action":{"action":"call-service","service":"input_select.select_option",
                          "service_data":{"entity_id":FILTER_ENTITY,"option":opt}}
        })
    cards.append({"type":"custom:mushroom-chips-card","chips":chips})

    # Dashboard-Update Button
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

    # Groups + Assets
    for gid in sorted(groups.keys()):
        gname = GROUP_NAMES.get(gid, f"Gruppe {gid}")
        gassets = groups[gid]

        cards.append({
            "type": "custom:mushroom-title-card",
            "title": gname,
            "card_mod": {"style": f":host {{ display: {{{{ 'block' if {show_group(gassets, gname)} else 'none' }}}}; }}"}
        })

        for a in gassets:
            s = a["s"]
            gn = a["gn"]
            cards.append({
                "type": "custom:mushroom-template-card",
                "entity": s,
                "primary": (f"{{{{ state_attr('{s}','label') | default('{a['label']}') }}}}"
                            f"{{%- if state_attr('{s}','radio_name') %}} · {{{{ state_attr('{s}','radio_name') }}}}{{%- endif %}}"
                            f"{{%- if state_attr('{s}','name') %}} · {{{{ state_attr('{s}','name') }}}}{{%- endif %}}"),
                "secondary": (f"{{{{ states('{s}') }}}}"
                              f"{{%- if state_attr('{s}','comment') and state_attr('{s}','comment')|trim|length > 0 %}}"
                              f" · {{{{ state_attr('{s}','comment') }}}}{{%- endif %}}"),
                "icon": icon_j(s),
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
                "card_mod": {"style": f":host {{ display: {{{{ 'block' if {show_asset(s, gn)} else 'none' }}}}; }}"}
            })

    return {
        "title": "STEIN",
        "views": [{"title":"STEIN","path":"stein","icon":"mdi:home-group","max_columns":1,"cards":cards}]
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    token = get_token()
    if not token:
        print("FEHLER: Kein Token gefunden. Bitte in /config/scripts/stein_token.txt ablegen.")
        sys.exit(1)

    print("Lade States von Home Assistant...")
    try:
        states = ha_get_states(token)
    except urllib.error.URLError as e:
        print(f"FEHLER: Kann HA nicht erreichen: {e}")
        sys.exit(1)

    assets = find_assets(states)
    print(f"Gefundene Assets: {len(assets)}")

    for a in assets:
        print(f"  [{a['group']}] {a['label']} → {a['entity_id']}")

    if not assets:
        print("FEHLER: Keine STEIN-Assets gefunden. Integration geladen?")
        sys.exit(1)

    dashboard = build_dashboard(assets)

    os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
    output = yaml.dump(dashboard, allow_unicode=True, sort_keys=False,
                       default_flow_style=False, width=200000)

    with open(DASHBOARD_FILE, "w") as f:
        f.write(output)

    print(f"\nDashboard gespeichert: {DASHBOARD_FILE}")
    print(f"Karten generiert: {len(dashboard['views'][0]['cards'])}")
    print("\nBitte Dashboard in HA neu laden (Browser F5 oder HA neu starten).")


if __name__ == "__main__":
    main()
