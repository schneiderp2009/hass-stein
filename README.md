# STEIN – Home Assistant Integration

Bindet die [STEIN API](https://stein.app) (Status Einsatz Meldung) in Home Assistant ein.

## Features

| Feature | Beschreibung |
|---|---|
| **Sensor** (pro Asset) | Zeigt den Status als Text auf Deutsch an |
| **Select** (pro Asset) | Status direkt aus der HA-Oberfläche ändern |
| **Sensor** (pro BU) | Gesamtübersicht Fahrzeuganzahl + Statusverteilung |
| **Service** `stein.update_asset_status` | Status + Kommentar per Automation setzen |
| **Auto-Discovery** | Neue Assets werden bei der nächsten Abfrage automatisch registriert |

## Installation

### HACS (empfohlen)

1. HACS öffnen → Integrationen → `+` → Custom Repository hinzufügen
2. URL: `https://github.com/DEIN_REPO/stein-ha` – Kategorie: Integration
3. Integration installieren und Home Assistant neu starten

### Manuell

```bash
cp -r custom_components/stein/ config/custom_components/stein/
```

Home Assistant neu starten.

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → STEIN**
2. Eingaben:
   - **API Bearer Token** – aus deinem STEIN-Konto
   - **BU-IDs** – kommagetrennt, z.B. `1,5,12`
   - **Abfrageintervall** – Standard: 60 Sekunden

## Entitäten

Nach der Einrichtung erscheinen:

- `sensor.stein_<label>` – Status-Sensor pro Fahrzeug/Asset
- `select.stein_<label>_status_setzen` – Status-Auswahl pro Fahrzeug
- `sensor.stein_bu_<name>_uebersicht` – Übersicht pro BU

### Sensor-Attribute (pro Asset)

| Attribut | Beschreibung |
|---|---|
| `status_raw` | API-Wert (`ready`, `inuse`, …) |
| `label` | Kurzbezeichnung |
| `name` | Vollname |
| `comment` | Kommentar |
| `category` | Kategorie |
| `radio_name` | Funkrufname |
| `issi` | ISSI (Digitalfunk) |
| `operation_reservation` | Einsatzreservierung |
| `hu_valid_until` | HU gültig bis |
| `last_modified` | Letzte Änderung |
| `last_modified_by` | Geändert von |

## Service: `stein.update_asset_status`

```yaml
service: stein.update_asset_status
data:
  asset_id: 42
  status: inuse
  comment: "Wird für Übung eingesetzt"
  notify_radio: false
```

### Status-Werte

| API-Wert | Bedeutung |
|---|---|
| `ready` | Einsatzbereit |
| `notready` | Nicht einsatzbereit |
| `semiready` | Bedingt einsatzbereit |
| `inuse` | Im Einsatz |
| `maint` | In Wartung |

## Beispiel-Automation

```yaml
alias: "LF1 auf Im Einsatz setzen wenn Alarm"
trigger:
  - platform: state
    entity_id: binary_sensor.alarmknopf
    to: "on"
action:
  - service: stein.update_asset_status
    data:
      asset_id: 7
      status: inuse
      comment: "Automatisch gesetzt bei Alarm"
```

## Beispiel-Lovelace-Karte

```yaml
type: entities
title: THW Fahrzeugstatus
entities:
  - entity: sensor.stein_lf1
    name: LF 1
  - entity: select.stein_lf1_status_setzen
    name: Status ändern
  - entity: sensor.stein_bu_ubersicht
    name: Gesamtübersicht
```
