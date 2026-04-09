# STEIN Dashboard Generator – Einrichtung

## Übersicht

Das Script `stein_dashboard_gen.py` liest alle STEIN-Asset-Entities direkt aus der
Home Assistant State Machine und generiert daraus eine vollständige `dashboard.yaml`.

**Vorteile:**
- Keine hardcodierten Entity-IDs – funktioniert mit jedem OV und jeder HA-Installation
- Neue Assets erscheinen automatisch nach erneutem Script-Aufruf
- Erkennt sowohl alte als auch neue Entity-ID-Varianten automatisch

---

## Einrichtung

### 1. Dateien kopieren

```bash
cp scripts/stein_dashboard_gen.py /config/scripts/
mkdir -p /config/dashboards
```

### 2. Long-Lived Access Token erstellen

1. HA öffnen → Profil (unten links) → **Langlebige Zugriffstoken**
2. Token erstellen → kopieren
3. Token speichern:

```bash
echo "dein_token_hier" > /config/scripts/stein_token.txt
chmod 600 /config/scripts/stein_token.txt
```

### 3. configuration.yaml ergänzen

```yaml
lovelace:
  mode: storage
  dashboards:
    stein-dashboard:
      mode: yaml
      title: STEIN
      icon: mdi:home-group
      show_in_sidebar: true
      filename: dashboards/stein.yaml

shell_command:
  stein_dashboard_rebuild: "python3 /config/scripts/stein_dashboard_gen.py"

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

### 4. HA neu starten

### 5. Dashboard erstmalig generieren

Per SSH/Terminal:
```bash
python3 /config/scripts/stein_dashboard_gen.py
```

Oder in HA: **Entwicklerwerkzeuge → Aktionen → `shell_command.stein_dashboard_rebuild`**

Das Script gibt eine Übersicht aller gefundenen Assets und ihrer Entity-IDs aus:
```
[1] GKW                → sensor.gkw_status
     select: select.gkw_status_setzen
     switch: switch.gkw_einsatzreservierung
     text:   text.gkw_bezeichnung, text.gkw_kommentar
```

### 6. Automation einrichten (optional)

Damit das Dashboard automatisch aktualisiert wird wenn neue Assets in STEIN angelegt werden:

In HA: **Einstellungen → Automationen → + Neue Automation → Als YAML bearbeiten**

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

## Manuelles Dashboard aktualisieren

Wenn neue Assets in STEIN hinzugekommen sind:

1. Script ausführen (per SSH oder Dashboard-Button):
   ```bash
   python3 /config/scripts/stein_dashboard_gen.py
   ```
2. Browser neu laden (F5)

---

## Konfiguration im Script anpassen

Oben im Script `stein_dashboard_gen.py` können folgende Werte angepasst werden:

```python
HA_URL         = "http://localhost:8123"   # HA-Adresse
TOKEN_FILE     = "/config/scripts/stein_token.txt"
DASHBOARD_FILE = "/config/dashboards/stein.yaml"
```
