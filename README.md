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
| 🔁 | **Auto-Discovery** | Neue Assets werden automatisch erkannt und als Entities angelegt |
| 🔄 | **Dashboard-Generator** | Script generiert das Dashboard automatisch aus den echten Entity-IDs |
| 🔒 | **Rate-Limit-Schutz** | 429-Fehler werden automatisch mit Retry behandelt |

---

## 📋 Voraussetzungen

### Home Assistant
- Home Assistant **2023.6.0** oder neuer
- Ein **STEIN-Konto** mit technischem Benutzer und API-Token
- IP-Adresse aus **Deutschland** (STEIN sperrt ausländische IPs)

### HACS Frontend-Erweiterungen (für das Dashboard)

| Card | Beschreibung |
|---|---|
| **Mushroom Cards** (`lovelace-mushroom`) | Moderne Karten für Status, Templates, Chips |
| **browser_mod** | Popup-Funktionalität für Asset-Details |
| **card-mod** (`lovelace-card-mod`) | CSS-Anpassungen für Filter-Sichtbarkeit |

Installation: HACS → Frontend → Suchen → Installieren → HA neu starten

---

## 🚀 Installation der Integration

### Via HACS (empfohlen)

1. HACS öffnen → **Integrationen** → Menü oben rechts → **Benutzerdefinierte Repositories**
2. URL eintragen: `https://github.com/DEIN_USERNAME/hass-stein`
3. Kategorie: **Integration** → Hinzufügen
4. Integration suchen → **Installieren**
5. Home Assistant neu starten

### Manuell

```bash
cp -r custom_components/stein/ /config/custom_components/stein/
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

> ⚠️ **Rate-Limit beachten:** STEIN erlaubt maximal 20 Anfragen/Minute. Das Standard-Intervall von 300 Sekunden ist bewusst konservativ. Bei einem 429-Fehler wartet die Integration automatisch 65 Sekunden und versucht es erneut. BU-Daten und Nutzerinfo werden nur alle ~50 Minuten abgerufen.

---

## 🗂️ Entitäten

Nach der Einrichtung erscheinen folgende Entitäten **pro Asset**:

| Entität | Typ | Beschreibung |
|---|---|---|
| `sensor.{slug}_status` | Sensor | Status + alle Felder als Attribute |
| `select.{slug}_status_setzen` | Select | Status umschalten |
| `text.{slug}_bezeichnung` | Text | Kurzbezeichnung bearbeiten |
| `text.{slug}_name` | Text | Vollname / Kennzeichen bearbeiten |
| `text.{slug}_kommentar` | Text | Kommentar bearbeiten |
| `text.{slug}_kategorie` | Text | Kategorie bearbeiten |
| `text.{slug}_funkrufname` | Text | Funkrufname bearbeiten |
| `text.{slug}_issi` | Text | ISSI (Digitalfunk) bearbeiten |
| `switch.{slug}_einsatzreservierung` | Switch | Einsatzreservierung an/aus |

> Der `{slug}` wird von HA aus dem Gerätenamen und Entity-Namen generiert, z.B. `gkw` für „GKW".

**Global:**

| Entität | Typ | Beschreibung |
|---|---|---|
| `sensor.stein_bu_{bu_id}` | Sensor | Ortsverband-Daten, Statistiken, Kontakt |
| `sensor.stein_api_stein_verbindung` | Sensor | Aktiver API-Nutzer, Scope, Berechtigungen |

---

### 📌 Status-Werte

| API-Wert | Anzeige | Symbol |
|---|---|---|
| `ready` | Einsatzbereit | ✅ grün |
| `notready` | Nicht einsatzbereit | ❌ rot |
| `semiready` | Bedingt einsatzbereit | ⚠️ orange |
| `inuse` | Im Einsatz | 🚒 blau |
| `maint` | In Wartung | 🔧 lila |

---

## 📊 Dashboard einrichten

Das Dashboard wird über ein Python-Script dynamisch generiert – es liest die echten Entity-IDs direkt aus HA und erstellt eine vollständige `dashboard.yaml` mit Filtern, Gruppen und Popups.

### Schritt 1: configuration.yaml ergänzen

```yaml
# Dashboard als YAML-Datei einbinden
lovelace:
  mode: storage
  dashboards:
    stein-dashboard:
      mode: yaml
      title: STEIN
      icon: mdi:home-group
      show_in_sidebar: true
      filename: dashboards/stein.yaml

# Shell Command für Dashboard-Rebuild
shell_command:
  stein_dashboard_rebuild: "python3 /config/scripts/stein_dashboard_gen.py"

# Filter-Helfer für das Dashboard
input_select:
  stein_filter:
    name: STEIN Filter
    options:
      - Alle
      - Fahrzeuge
      - Geraete
      - Sonderfunktionen
      - Einheiten
      - Anhaenger
      - Probleme
      - Bereit
      - Bedingt
      - Nicht bereit
      - Im Einsatz
      - Wartung
    initial: Alle
    icon: mdi:filter
```

### Schritt 2: Script und Token einrichten

```bash
# Script kopieren
cp scripts/stein_dashboard_gen.py /config/scripts/

# Long-Lived Access Token erstellen:
# HA → Profil → Langlebige Zugriffstoken → Token erstellen → kopieren
echo "DEIN_TOKEN_HIER" > /config/scripts/stein_token.txt
chmod 600 /config/scripts/stein_token.txt

# Dashboard-Ordner anlegen
mkdir -p /config/dashboards
```

### Schritt 3: HA neu starten

### Schritt 4: Dashboard erstmalig generieren

```bash
python3 /config/scripts/stein_dashboard_gen.py
```

Oder in HA: **Entwicklerwerkzeuge → Aktionen → `shell_command.stein_dashboard_rebuild`**

### Schritt 5: Automation einrichten (optional)

In HA unter **Einstellungen → Automationen → + Neue Automation → Als YAML bearbeiten**:

```yaml
alias: "STEIN Dashboard auto-rebuild"
trigger:
  - platform: event
    event_type: entity_registry_updated
    event_data:
      action: create
condition:
  - condition: template
    value_template: "{{ 'stein' in trigger.event.data.get('entity_id','') }}"
action:
  - delay: "00:00:10"
  - service: shell_command.stein_dashboard_rebuild
  - service: persistent_notification.create
    data:
      title: "STEIN Dashboard"
      message: "Dashboard wurde automatisch aktualisiert – bitte Seite neu laden (F5)."
      notification_id: "stein_dashboard_rebuild"
```

---

## 🛠️ Service: `stein.update_asset`

Alle Felder eines Assets per Automation oder Skript ändern:

```yaml
service: stein.update_asset
data:
  asset_id: 340
  status: inuse
  label: "GKW"
  name: "THW-12345"
  comment: "Im Einsatz"
  category: "Fahrzeug"
  radio_name: "22/51"
  issi: "1234567"
  sort_order: 1
  operation_reservation: true
  hu_valid_until: "2027-06-30T00:00:00Z"
  notify_radio: false
```

> Nur angegebene Felder werden geändert – alle anderen bleiben unverändert.

---

## 🤖 Beispiel-Automationen

### Fahrzeug bei Alarm auf „Im Einsatz" setzen

```yaml
alias: "GKW – Alarm → Im Einsatz"
trigger:
  - platform: state
    entity_id: binary_sensor.alarmknopf
    to: "on"
action:
  - service: stein.update_asset
    data:
      asset_id: 340
      status: inuse
      comment: "Automatisch gesetzt – Alarm"
```

### Benachrichtigung bei Ausfall

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
IP muss aus Deutschland sein – STEIN sperrt ausländische IPs.

**`429 Too Many Requests`:**
Die Integration wartet automatisch 65 Sekunden und versucht es erneut. Abfrageintervall unter **Konfigurieren** erhöhen falls es wiederholt auftritt (mindestens 300 Sekunden empfohlen).

**Popup öffnet sich nicht:**
Sicherstellen dass `browser_mod` korrekt installiert und in HA registriert ist. Nach der Installation einmal HA neu starten.

**Felder im Popup zeigen „unavailable":**
Das Dashboard-Generator-Script neu ausführen – es liest die aktuellen Entity-IDs aus HA:
```bash
python3 /config/scripts/stein_dashboard_gen.py
```

**Dashboard zeigt alle Assets als „unknown":**
Die Integration wurde neu eingerichtet und die Entity-IDs haben sich geändert. Generator-Script neu ausführen.

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
