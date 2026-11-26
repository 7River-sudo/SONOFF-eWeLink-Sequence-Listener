# SONOFF eWeLink Sequence Listener

Lokale Home-Assistant-Custom-Integration für SONOFF MINIR4M im
**Detach-Relay-Modus**, wenn der externe S1/S2-Schalter über Matter nicht als
eigenes Ereignis bereitgestellt wird.

## Konzept

Der MINIR4M veröffentlicht über `_ewelink._tcp.local.` unverschlüsselte
Metadaten und eine unverschlüsselte `seq`-Nummer. Der eigentliche Payload ist
bei normaler Firmware verschlüsselt (`encrypt=true`), aber für diesen
Workaround wird nur eine Änderung der `seq` ausgewertet.

Die Integration:

- nutzt **einen einzigen gemeinsamen mDNS/Zeroconf-Listener**
- kann **beliebig viele Relais** verwalten
- gibt jedem Relais einen **frei wählbaren Namen**
- legt jedes Relais als eigenes **Home-Assistant-Gerät** an
- erstellt je Gerät einen deaktiviert-unaufdringlichen Diagnosewert `Sequence`
- ignoriert IPv4-/IPv6-Duplikate mit derselben `seq`
- verwendet den ersten Wert nach Start als Baseline
- unterdrückt nach einer längeren mDNS-Trennung den ersten neuen Wert als Baseline
- feuert bei einer echten Änderung ein HA-Event `sonoff_seq_change`

## Installation

Kopiere:

    custom_components/sonoff_seq

nach:

    /config/custom_components/sonoff_seq

Danach Home Assistant **vollständig neu starten**.

Anschließend:

1. Einstellungen → Geräte & Dienste
2. Integration hinzufügen
3. `SONOFF eWeLink Sequence Listener`
4. Device-ID eingeben, z. B. `1000abcdef`
5. frei wählbaren Namen vergeben, z. B. `exampleroom - light`

Für jedes weitere Relais die Integration erneut hinzufügen. Intern bleibt es
trotzdem **ein gemeinsamer mDNS-Listener**.

## Device-ID finden

Auf einem Rechner im Netz:

    avahi-browse -rt _ewelink._tcp

Beispiel:

    eWeLink_1000abcdef

Die Device-ID ist dann:

    1000abcdef

## Event

Bei einer Änderung:

    event_type: sonoff_seq_change

Beispieldaten:

    entry_id: "..."
    device_id: "1000abcdef"
    name: "exampleroom - light"
    old_seq: "49"
    seq: "50"

## Empfohlener Test

Zuerst NICHT direkt die light toggeln, sondern eine Benachrichtigung erzeugen:

```yaml
alias: TEST - light Sonoff Seq
triggers:
  - trigger: event
    event_type: sonoff_seq_change
    event_data:
      device_id: "1000abcdef"

actions:
  - action: persistent_notification.create
    data:
      title: "SONOFF Schalter erkannt"
      message: >-
        {{ trigger.event.data.name }}:
        seq {{ trigger.event.data.old_seq }} → {{ trigger.event.data.seq }}

mode: single
```

Wenn nur echte Wippenbetätigungen Ereignisse erzeugen, kann danach die
Light-Automation verwendet werden:

```yaml
alias: exampleroom - light
triggers:
  - trigger: event
    event_type: sonoff_seq_change
    event_data:
      device_id: "1000abcdef"

actions:
  - action: light.toggle
    target:
      entity_id: light.example

mode: single
```

## Wichtige Einschränkung

Die Integration kann den verschlüsselten eWeLink-Payload **nicht** lesen.
Darum kann sie nicht kryptografisch unterscheiden, ob eine `seq`-Änderung
wirklich von S1/S2 oder von einer anderen Geräteaktion stammt.

Vor dem dauerhaften Einsatz sollte das jeweilige Relais deshalb zunächst über
mehrere Stunden beobachtet werden. Ein ungewolltes `seq`-Event würde sonst
ebenfalls die Automation auslösen.


## v0.3.0 – fester virtueller EIN/AUS-Zustand

Zusätzlich zum Diagnose-Sensor `Sequence` legt jedes Gerät jetzt einen
virtuellen Schalter `Wandschalter` an.

Wichtig: Dieser virtuelle Schalter steuert NICHT das physische Relais des
MINIR4M. Er bildet nur die S1/S2-Wippe als festen ON/OFF-Zustand ab.

Jede bestätigte `seq`-Änderung schaltet:

    off -> on -> off -> on ...

Der virtuelle Zustand wird über Home-Assistant-Neustarts gespeichert.

### Einmal synchronisieren

Da der verschlüsselte eWeLink-Payload nicht verrät, welche Wippenstellung
physisch EIN oder AUS ist:

1. Wippe in die Stellung bringen, die künftig AUS sein soll.
2. In Home Assistant die Entität `Wandschalter` einmal manuell auf AUS setzen.
3. Danach entsprechen die beiden Wippenstellungen fest EIN/AUS, solange keine
   Schalterereignisse während einer längeren HA-Ausfallzeit verpasst werden.

Wenn die Zuordnung einmal nicht mehr stimmt, den virtuellen `Wandschalter`
einfach erneut manuell auf die aktuelle physische Stellung synchronisieren.

### Automation mit festem EIN/AUS

```yaml
alias: exampleroom - light
triggers:
  - trigger: state
    entity_id:
      - switch.exampleroom_seq_wallswitch
    to: "on"
    id: "on"

  - trigger: state
    entity_id:
      - switch.exampleroom_seq_wallswitch
    to: "off"
    id: "off"

actions:
  - choose:
      - conditions:
          - condition: trigger
            id: "on"
        sequence:
          - action: light.turn_on
            target:
              entity_id: light.example

      - conditions:
          - condition: trigger
            id: "off"
        sequence:
          - action: light.turn_off
            target:
              entity_id: light.example

mode: single
```

Das Event `sonoff_seq_change` enthält zusätzlich `switch_state: on|off`.
