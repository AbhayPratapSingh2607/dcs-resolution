# On Station start

In Retribution a flight starts cold, warm, on the runway or in the air over its base. Support assets
therefore take off when the mission starts, and the usual workaround is to fast-forward until they
arrive. In reality, AWACS, tankers and combat air patrols would already be airborne and on station.

Resolution adds a fifth start type, **On Station**. A flight with this start type appears in the air
at its station, at the time its flight plan has it there.

## Using it

1. In the flight's **Start type** dropdown, choose **On Station**. This is in the flight creator
   and on the flight's **General Flight settings** tab.
2. To have the flight on station when the mission starts, tick **ASAP** on the package. The
   package TOT then becomes the earliest time the package can be on station. For an AWACS, tanker
   or CAP package where every flight is On Station, that is mission start.
3. Otherwise, the flight appears at its station at its normal planned time. It is late-activated
   until then.

You can also make On Station the default under **Settings → Mission Generator → Gameplay**, with
**Default start type for AI aircraft** or **Default start type for Player flights**. The AI default
applies to every AI flight, attack packages included. Off-map spawns always start In Flight.

## Where the station is

| Flight | Station |
|---|---|
| BARCAP, TARCAP, AWACS, tanker, CAS | The start of the racetrack (patrol start) |
| Fighter sweep | The start of the sweep |
| Strike, SEAD, DEAD, BAI, anti-ship, OCA and their escorts | The IP (ingress point) |
| Escort of an AWACS or tanker | Where it meets the AWACS or tanker at the package TOT |
| Other formation flights | The join point, or the hold point |
| Ferry, transport, custom flight plans | No station: these start in the air over their base, like In Flight |

The flight spawns at its station's planned altitude and speed. It then flies the rest of its flight
plan as usual: it holds its racetrack until the planned departure time, or flies from the IP to the
target, then home.

## Notes

* **Package timing.** If some flights in a package start On Station and others don't, the package
  timing still works: each flight appears or takes off at its own planned time. With ASAP ticked,
  the slowest flight sets the package TOT. For example, a cold-start escort delays an On Station
  AWACS.
* **Already past the station.** A flight whose station time is before mission start (for example,
  a SEAD sweep ahead of an ASAP strike package) spawns further along its route, where its plan has
  it at mission start.
* **Fuel.** The flight starts with the fuel it would have left after flying out to its station.
* **Fast forward.** A player flight that starts On Station stops fast-forwarding when it appears,
  for the "Player startup", "Player taxi" and "Player takeoff" stop conditions. It also stops at
  the IP for "Player at IP".
* **OCA targets.** Like any start other than Cold, On Station aircraft are not parked at the base,
  so OCA/Aircraft strikes can't hit them.
* **Pretense.** Pretense campaigns treat On Station as an air start over the base.
