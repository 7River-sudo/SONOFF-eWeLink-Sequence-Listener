# SONOFF eWeLink Sequence Listener

**🇬🇧 English** | [🇩🇪 Deutsch](README.de.md)

Local Home Assistant custom integration for SONOFF MINIR4M in
**Detach Relay Mode**, when the external S1/S2 switch is not exposed as a
separate event via Matter.

## Concept

The MINIR4M publishes unencrypted metadata and an unencrypted `seq` number
via `_ewelink._tcp.local.`. With standard firmware, the actual payload is
encrypted (`encrypt=true`), but this workaround only evaluates changes to
`seq`.

The integration:

- uses **a single shared mDNS/Zeroconf listener**
- can manage **any number of relays**
- assigns each relay a **freely configurable name**
- creates a separate **Home Assistant device** for each relay
- creates a diagnostic sensor named `Sequence` for each device
- ignores IPv4/IPv6 duplicates with the same `seq`
- uses the first value after startup as a baseline
- suppresses the first new value after a prolonged mDNS disconnection by treating it as a baseline
- fires a Home Assistant event named `sonoff_seq_change` when an actual change occurs

## Installation

Copy:

    custom_components/sonoff_seq

to:

    /config/custom_components/sonoff_seq

Then **restart Home Assistant completely**.

Next:

1. Settings → Devices & services
2. Add integration
3. `SONOFF eWeLink Sequence Listener`
4. Enter the device ID, e.g. `1000abcdef`
5. Assign a name of your choice, e.g. `exampleroom - light`

Add the integration again for each additional relay. Internally, it still
uses **a single shared mDNS listener**.

## Finding the device ID

On a computer on the network:

    avahi-browse -rt _ewelink._tcp

Example:

    eWeLink_1000abcdef

The device ID is then:

    1000abcdef

## Event

When a change occurs:

    event_type: sonoff_seq_change

Example data:

    entry_id: "..."
    device_id: "1000abcdef"
    name: "exampleroom - light"
    old_seq: "49"
    seq: "50"

The device IDs, device names and entity IDs used here are fictional examples and must be adapted to your own Home Assistant installation.

## Recommended test

Do NOT toggle `light.example` directly at first. Create a notification instead:

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
      title: "SONOFF switch detected"
      message: >-
        {{ trigger.event.data.name }}:
        seq {{ trigger.event.data.old_seq }} → {{ trigger.event.data.seq }}

mode: single
```

If only actual rocker switch operations generate events, the light automation
can then be used:

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

## Important limitation

The integration **cannot** read the encrypted eWeLink payload.
It therefore cannot cryptographically distinguish whether a change in `seq`
actually originates from S1/S2 or from another device action.

Before permanent use, the relay should be monitored for several hours.
An unintended `seq` event would otherwise also trigger the automation.

The mDNS data being evaluated is not authenticated. Manipulated messages on the local network can trigger unintended switching operations. The integration is therefore not intended for safety-critical applications.


## v0.3.0 – fixed virtual ON/OFF state

In addition to the `Sequence` diagnostic sensor, each device now creates a
virtual switch named `Wandschalter` (wall switch).

Important: This virtual switch does NOT control the physical relay of the
MINIR4M. It only represents the S1/S2 rocker switch as a fixed ON/OFF state.

Each confirmed change in `seq` toggles the state:

    off -> on -> off -> on ...

The virtual state is preserved across Home Assistant restarts.

### Initial synchronization

Because the encrypted eWeLink payload does not reveal which physical rocker
position is ON or OFF:

1. Move the rocker to the position that should represent OFF.
2. Manually set the `Wandschalter` entity to OFF in Home Assistant once.
3. The two rocker positions then correspond to fixed ON/OFF states, as long as no
   switch events are missed during an extended Home Assistant outage.

If the mapping becomes incorrect, simply resynchronize the virtual
`Wandschalter` with the current physical switch position manually.

### Automation with fixed ON/OFF

```yaml
alias: exampleroom - light
triggers:
  - trigger: state
    entity_id:
      - switch.exampleroom_light_wandschalter
    to: "on"
    id: "on"

  - trigger: state
    entity_id:
      - switch.exampleroom_light_wandschalter
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

The `sonoff_seq_change` event also includes `switch_state: on|off`.

## License

This project is licensed under the [Sustainable Use License 1.0](LICENSE.md).
