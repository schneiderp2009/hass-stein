update_asset:
  name: Asset aktualisieren
  description: >
    Aktualisiert ein STEIN-Asset. Nur angegebene Felder werden geändert,
    alle anderen bleiben unverändert.
  fields:
    asset_id:
      name: Asset-ID
      description: Die numerische ID des Assets.
      required: true
      example: 42
      selector:
        number:
          min: 1
          mode: box
    status:
      name: Status
      description: Der neue Status des Assets.
      required: false
      example: ready
      selector:
        select:
          options:
            - ready
            - notready
            - semiready
            - inuse
            - maint
    label:
      name: Bezeichnung
      description: Kurzbezeichnung des Assets (max. 255 Zeichen).
      required: false
      example: "LF 1"
      selector:
        text:
    name:
      name: Name
      description: Vollständiger Name des Assets (max. 255 Zeichen).
      required: false
      example: "Löschfahrzeug 1"
      selector:
        text:
    comment:
      name: Kommentar
      description: Kommentar zum Asset (max. 25000 Zeichen).
      required: false
      example: "Ölwechsel abgeschlossen"
      selector:
        text:
          multiline: true
    category:
      name: Kategorie
      description: Kategorie des Assets (max. 45 Zeichen).
      required: false
      example: "Fahrzeug"
      selector:
        text:
    radio_name:
      name: Funkrufname
      description: Funkrufname des Assets (max. 255 Zeichen).
      required: false
      example: "Florian 1"
      selector:
        text:
    issi:
      name: ISSI
      description: ISSI (Digitalfunk, max. 255 Zeichen).
      required: false
      example: "1234567"
      selector:
        text:
    sort_order:
      name: Sortierung
      description: Sortierreihenfolge des Assets.
      required: false
      example: 10
      selector:
        number:
          min: 0
          mode: box
    operation_reservation:
      name: Einsatzreservierung
      description: Gibt an ob das Asset für einen Einsatz reserviert ist.
      required: false
      selector:
        boolean:
    hu_valid_until:
      name: HU gültig bis
      description: Datum bis wann die Hauptuntersuchung gültig ist (ISO 8601).
      required: false
      example: "2026-12-31T00:00:00Z"
      selector:
        text:
    notify_radio:
      name: Radio-Benachrichtigung
      description: E-Mail-Benachrichtigung bei Änderung des Funkrufnamens senden.
      required: false
      default: false
      selector:
        boolean:
