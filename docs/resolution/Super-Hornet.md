# Super Hornet

Resolution includes several fixes for the **CJS F/A-18E/F/G Super Hornet** mod. Enable it as usual in
the **New Game** wizard's mod options.

## CJS Super Hornet v2.4.6 payloads

In Retribution, creating a Super Hornet flight fails with *"could not convert string to float"* when
v2.4.6 of the mod is installed. That version writes its payload files with keys such as `[WTL]` after
a line like `local WTL = 1`, and pydcs' Lua parser accepts only numbers and strings as keys.
Resolution replaces those constants with their values before the file is parsed, and leaves keys
inside quoted strings alone. Super Hornet flights can then be created normally.

## Other fixes

* **Weapon names:** the Super Hornet's pylon weapons now use the current pydcs weapon identifiers,
  so stores aren't missing or misidentified.
* **Callsigns:** the mod's callsign table was malformed: it was a plain list rather than a list per
  country. It is now fixed, and the Super Hornets use Hornet-squadron callnames such as Hornet, Ragin,
  Sting, Jury and Joker.
* **Station labels:** the payload editor shows the mod's own station labels. The cheek station reads
  `5 | 4`, and the EA-18G's wingtip pods read `3B` and `9B`. See [Loadout editor](Loadout-Editor.md).
* **Payload names:** CJS payloads are listed by their mission editor labels, such as
  "USN Adv. Extended Range CAP", instead of their short internal names.
