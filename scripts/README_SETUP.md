# STEIN Dashboard Generator – Einrichtung

## 1. Dateien kopieren

```bash
cp /config/custom_components/stein/scripts/stein_dashboard_gen.py /config/scripts/
```

## 2. Long-Lived Access Token erstellen

1. HA öffnen → Profil (unten links) → "Langlebige Zugriffstoken"
2. Token erstellen → kopieren
3. Speichern in `/config/scripts/stein_token.txt`

```bash
echo "dein_token_hier" > /config/scripts/stein_token.txt
chmod 600 /config/scripts/stein_token.txt
```

## 3. Dashboard-Ordner anlegen

```bash
mkdir -p /config/dashboards
```

## 4. configuration.yaml ergänzen

```yaml
# Dashboard als YAML-Datei registrieren
lovelace:
  mode: storage
  dashboards:
    stein-dashboard:
      mode: yaml
      title: STEIN
      icon: mdi:home-group
      show_in_sidebar: true
      filename: dashboards/stein.yaml

# Shell Command fuer Rebuild
shell_command:
  stein_dashboard_rebuild: "python3 /config/scripts/stein_dashboard_gen.py"

# input_select fuer Filter
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

## 5. HA neu starten

## 6. Erstes Dashboard generieren

Entweder per SSH:
```bash
python3 /config/scripts/stein_dashboard_gen.py
```

Oder in HA: Entwicklerwerkzeuge → Aktionen:
```yaml
action: shell_command.stein_dashboard_rebuild
```

## 7. Automatische Aktualisierung (optional)

In configuration.yaml oder automation.yaml:

```yaml
automation:
  - alias: "STEIN Dashboard auto-rebuild"
    trigger:
      - platform: event
        event_type: entity_registry_updated
        event_data:
          action: create
    condition:
      - condition: template
        value_template: "{{ 'stein' in trigger.event.data.get('entity_id','') }}"
    action:
      - delay: "00:00:05"
      - service: shell_command.stein_dashboard_rebuild
```

## Funktionsweise

Das Script:
1. Fragt alle States von HA ab (REST API)
2. Findet alle `sensor.*_status` Entities mit `status_raw` + `bu_id` Attribut
3. Gruppiert nach `group_id`
4. Generiert komplettes Dashboard YAML mit Filtern, Popups, Bearbeitungsfeldern
5. Speichert nach `/config/dashboards/stein.yaml`

Das Dashboard wird automatisch aktualisiert wenn neue Assets in STEIN hinzukommen
und das Script erneut ausgeführt wird – entweder manuell per Button im Dashboard
oder automatisch per Automation.
