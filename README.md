<div align="center">

# 🚒 STEIN für Home Assistant

**Status Einsatz Meldung – Fahrzeugstatus deines THW-Ortsverbands direkt in Home Assistant**

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge&logo=home-assistant)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-blue?style=for-the-badge&logo=home-assistant)](https://www.home-assistant.io)
[![License](https://img.shields.io/badge/Lizenz-MIT-green?style=for-the-badge)](LICENSE)

---

*Lese und steuere den Einsatzstatus deiner Fahrzeuge, Anhänger und Geräte direkt aus Home Assistant heraus – vollständig integriert in Dashboards, Automationen und Benachrichtigungen.*

</div>

---

## ✨ Features

| | Feature | Beschreibung |
|---|---|---|
| 📊 | **Status-Sensor** | Einsatzstatus jedes Assets auf Deutsch, alle API-Felder als Attribute |
| 🔄 | **Status wechseln** | Direkt per Dropdown in der HA-Oberfläche |
| ✏️ | **Felder bearbeiten** | Bezeichnung, Name, Kommentar, Kategorie, Funkrufname, ISSI |
| 🔖 | **Einsatzreservierung** | Ein/Aus per Toggle-Schalter |
| 🏠 | **BU-Übersicht** | Gesamtstatus des Ortsverbands mit Fahrzeugzählung |
| 👤 | **Verbindungsstatus** | Sensor zeigt aktiven API-Nutzer und Zugriffsrechte |
| ⚙️ | **Service** | Alle Felder per Automation oder Skript änderbar |
| 🔁 | **Auto-Discovery** | Neue Assets werden automatisch erkannt |

---

## 📋 Voraussetzungen

- Home Assistant **2023.6.0** oder neuer
- Ein **STEIN-Konto** mit technischem Benutzer und API-Token
- IP-Adresse aus **Deutschland** (STEIN sperrt ausländische IPs)

---

## 🚀 Installation

### Via HACS (empfohlen)

1. HACS öffnen → **Integrationen** → Menü oben rechts → **Benutzerdefinierte Repositories**
2. URL eintragen: `https://github.com/DEIN_USERNAME/hass-stein`
3. Kategorie: **Integration** → Hinzufügen
4. Integration suchen → **Installieren**
5. Home Assistant neu starten

### Manuell

```bash
# In deinem HA config-Verzeichnis:
cp -r custom_components/stein/ config/custom_components/stein/
```

Home Assistant neu starten.

---

## ⚙️ Einrichtung

1. **Einstellungen → Geräte & Dienste → + Integration hinzufügen**
2. Nach **STEIN** suchen
3. Eingaben ausfüllen:

| Feld | Beschreibung | Beispiel |
|---|---|---|
| **API Bearer Token** | Token des technischen Benutzers aus STEIN | `eyJ0...` |
| **BU-IDs** | Kommagetrennte IDs deiner Ortsverbände | `19` oder `19,42` |
| **Abfrageintervall** | Sekunden zwischen Abfragen (min. 120) | `300` |

> ⚠️ **Rate-Limit beachten:** STEIN erlaubt maximal 20 Anfragen/Minute. Das Standard-Intervall von 300 Sekunden ist bewusst konservativ gewählt. BU-Daten und Nutzerinfo werden nur alle ~50 Minuten abgerufen.

---

## 🗂️ Entitäten

Nach der Einrichtung erscheinen folgende Entitäten **pro Asset** (Fahrzeug/Anhänger/Gerät):

| Entität | Typ | Beschreibung |
|---|---|---|
| `sensor.stein_<label>` | Sensor | Status + alle Felder als Attribute |
| `select.stein_<label>_status` | Select | Status umschalten |
| `text.stein_<label>_bezeichnung` | Text | Kurzbezeichnung bearbeiten |
| `text.stein_<label>_name` | Text | Vollname bearbeiten |
| `text.stein_<label>_kommentar` | Text | Kommentar bearbeiten |
| `text.stein_<label>_kategorie` | Text | Kategorie bearbeiten |
| `text.stein_<label>_funkrufname` | Text | Funkrufname bearbeiten |
| `text.stein_<label>_issi` | Text | ISSI (Digitalfunk) bearbeiten |
| `switch.stein_<label>_einsatzreservierung` | Switch | Einsatzreservierung an/aus |

**Pro BU (Ortsverband):**

| Entität | Typ | Beschreibung |
|---|---|---|
| `sensor.stein_<bu>_uebersicht` | Sensor | Gesamtzahl Fahrzeuge + Statusverteilung |

**Global:**

| Entität | Typ | Beschreibung |
|---|---|---|
| `sensor.stein_verbindung` | Sensor | Aktiver API-Nutzer, Scope, Berechtigungen |

---

### 📌 Status-Werte

| API-Wert | Anzeige | Symbol |
|---|---|---|
| `ready` | Einsatzbereit | ✅ |
| `notready` | Nicht einsatzbereit | ❌ |
| `semiready` | Bedingt einsatzbereit | ⚠️ |
| `inuse` | Im Einsatz | 🚒 |
| `maint` | In Wartung | 🔧 |

---

## 🛠️ Service: `stein.update_asset`

Ermöglicht das Ändern aller Felder eines Assets per Automation oder Skript.

```yaml
service: stein.update_asset
data:
  asset_id: 42            # Pflicht – numerische Asset-ID
  status: inuse           # optional
  label: "LF 1"          # optional – Kurzbezeichnung
  name: "Löschfahrzeug"  # optional – Vollname
  comment: "Im Einsatz"  # optional
  category: "Fahrzeug"   # optional
  radio_name: "Florian 1-42"  # optional
  issi: "1234567"        # optional
  sort_order: 10          # optional
  operation_reservation: true  # optional
  hu_valid_until: "2027-06-30T00:00:00Z"  # optional
  notify_radio: false     # optional – E-Mail bei Funkrufname-Änderung
```

> Nur die angegebenen Felder werden geändert – alle anderen bleiben unverändert.

---

## 🤖 Beispiel-Automationen

### Fahrzeug bei Alarm automatisch auf „Im Einsatz" setzen

```yaml
alias: "LF1 – Alarm → Im Einsatz"
trigger:
  - platform: state
    entity_id: binary_sensor.alarmknopf
    to: "on"
action:
  - service: stein.update_asset
    data:
      asset_id: 42
      status: inuse
      comment: "Automatisch gesetzt – Alarm"
```

### Benachrichtigung wenn Fahrzeug nicht einsatzbereit

```yaml
alias: "STEIN – Warnung bei Ausfall"
trigger:
  - platform: state
    entity_id: select.stein_lf1_status
    to: "Nicht einsatzbereit"
action:
  - service: notify.mobile_app_handy
    data:
      title: "⚠️ STEIN Warnung"
      message: "LF 1 ist nicht einsatzbereit!"
```

---

## 🗃️ Beispiel-Dashboard

```yaml
type: entities
title: 🚒 THW Fahrzeugstatus
entities:
  - entity: sensor.stein_verbindung
    name: API Verbindung
  - entity: sensor.stein_bu_uebersicht
    name: Ortsverband Übersicht
  - type: divider
  - entity: sensor.stein_lf1
    name: LF 1 – Status
  - entity: select.stein_lf1_status
    name: Status ändern
  - entity: switch.stein_lf1_einsatzreservierung
    name: Einsatzreservierung
```

---

## 🔍 Fehlerbehebung

**`cannot_connect` beim Setup:**
- Token prüfen: `curl -H "Authorization: Bearer TOKEN" https://stein.app/api/api/ext/userinfo`
- IP muss aus Deutschland sein (STEIN sperrt ausländische IPs)

**`429 Too Many Requests`:**
- Abfrageintervall erhöhen (mindestens 300 Sekunden empfohlen)
- Debug-Logging in `configuration.yaml` aktivieren:
  ```yaml
  logger:
    logs:
      custom_components.stein: debug
  ```

**Entitäten erscheinen nicht:**
- Unter **Einstellungen → Geräte & Dienste → STEIN** prüfen ob Geräte erkannt wurden
- Logs unter **Einstellungen → System → Protokolle** prüfen

---

## 📄 Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

<div align="center">

Entwickelt für den Einsatz beim **Technischen Hilfswerk** 🟦 und anderen Hilfsorganisationen.

*Kein offizielles STEIN-Produkt. Diese Integration ist ein Community-Projekt.*

</div>
