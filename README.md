<div align="center">

# 🚒 STEIN für Home Assistant

**Status Einsatz Meldung – Fahrzeugstatus deines THW-Ortsverbands direkt in Home Assistant**

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge&logo=home-assistant)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2023.6%2B-blue?style=for-the-badge&logo=home-assistant)](https://www.home-assistant.io)
[![License](https://img.shields.io/badge/Lizenz-MIT-green?style=for-the-badge)](LICENSE)

*Lese und steuere den Einsatzstatus deiner Fahrzeuge, Anhänger und Geräte direkt aus Home Assistant heraus.*

</div>

---

## ✨ Features

| | Feature | Beschreibung |
|---|---|---|
| 📊 | **Status-Sensor** | Einsatzstatus jedes Assets auf Deutsch, alle API-Felder als Attribute |
| 🔄 | **Status wechseln** | Direkt per Dropdown in der HA-Oberfläche |
| ✏️ | **Felder bearbeiten** | Bezeichnung, Name, Kommentar, Kategorie, Funkrufname, ISSI |
| 🔖 | **Einsatzreservierung** | Ein/Aus per Toggle-Schalter |
| 👤 | **Verbindungsstatus** | Sensor zeigt aktiven API-Nutzer und Zugriffsrechte |
| ⚙️ | **Service** | Alle Felder per Automation oder Skript änderbar |
| 🔁 | **Auto-Discovery** | Neue Assets werden automatisch erkannt |
| 🔒 | **Rate-Limit-Schutz** | 429-Fehler werden automatisch mit Retry behandelt |

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
cp -r custom_components/stein/ config/custom_components/stein/
```

Home Assistant neu starten.

---

## ⚙️ Einrichtung

1. **Einstellungen → Geräte & Dienste → + Integration hinzufügen → STEIN**
2. Eingaben:

| Feld | Beschreibung | Beispiel |
|---|---|---|
| **API Bearer Token** | Token des technischen Benutzers aus STEIN | `eyJ0...` |
| **BU-IDs** | Kommagetrennte IDs deiner Ortsverbände | `19` oder `19,42` |

Das Abfrageintervall (Standard: 300 Sekunden) kann nach der Einrichtung unter **Einstellungen → Geräte & Dienste → STEIN → Konfigurieren** angepasst werden.

> ⚠️ **Rate-Limit beachten:** STEIN erlaubt maximal 20 Anfragen/Minute. Das Standard-Intervall von 300 Sekunden ist bewusst konservativ gewählt. BU-Daten und Nutzerinfo werden nur alle ~50 Minuten abgerufen.

---

## 🗂️ Entitäten

Nach der Einrichtung erscheinen folgende Entitäten **pro Asset**:

| Entität | Typ | Beschreibung |
|---|---|---|
| `sensor.<label>_status` | Sensor | Status + alle Felder als Attribute |
| `select.<label>_status_setzen` | Select | Status umschalten |
| `text.<label>_bezeichnung` | Text | Kurzbezeichnung bearbeiten |
| `text.<label>_name` | Text | Vollname bearbeiten |
| `text.<label>_kommentar` | Text | Kommentar bearbeiten |
| `text.<label>_kategorie` | Text | Kategorie bearbeiten |
| `text.<label>_funkrufname` | Text | Funkrufname bearbeiten |
| `text.<label>_issi` | Text | ISSI (Digitalfunk) bearbeiten |
| `switch.<label>_einsatzreservierung` | Switch | Einsatzreservierung an/aus |

**Global:**

| Entität | Typ | Beschreibung |
|---|---|---|
| `sensor.stein_api_stein_verbindung` | Sensor | Aktiver API-Nutzer, Scope, Berechtigungen |

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

Alle Felder eines Assets per Automation oder Skript ändern:

```yaml
service: stein.update_asset
data:
  asset_id: 42
  status: inuse
  label: "LF 1"
  name: "Löschfahrzeug"
  comment: "Im Einsatz"
  category: "Fahrzeug"
  radio_name: "Florian 1-42"
  issi: "1234567"
  sort_order: 10
  operation_reservation: true
  hu_valid_until: "2027-06-30T00:00:00Z"
  notify_radio: false
```

> Nur angegebene Felder werden geändert – alle anderen bleiben unverändert.

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
    entity_id: sensor.gkw_status
    to: "Nicht einsatzbereit"
action:
  - service: notify.mobile_app_handy
    data:
      title: "⚠️ STEIN Warnung"
      message: "GKW ist nicht einsatzbereit!"
```

---

## 🔍 Fehlerbehebung

**`cannot_connect` beim Setup:**
```bash
curl -H "Authorization: Bearer TOKEN" https://stein.app/api/api/ext/userinfo
```
IP muss aus Deutschland sein (STEIN sperrt ausländische IPs).

**`429 Too Many Requests`:**
Die Integration wartet automatisch 65 Sekunden und versucht es erneut. Falls es wiederholt auftritt: Abfrageintervall unter **Konfigurieren** erhöhen (mindestens 300 Sekunden empfohlen).

**Debug-Logging aktivieren** – in `configuration.yaml`:
```yaml
logger:
  logs:
    custom_components.stein: debug
```

---

## 📄 Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

<div align="center">

Entwickelt für den Einsatz beim **Technischen Hilfswerk** 🟦 und anderen Hilfsorganisationen.

*Kein offizielles STEIN-Produkt. Diese Integration ist ein Community-Projekt.*

</div>
