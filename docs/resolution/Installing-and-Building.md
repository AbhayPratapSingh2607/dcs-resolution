# Installing and building

## Installing a packaged build

1. Download a build from the [Releases page](https://github.com/AbhayPratapSingh2607/dcs-resolution/releases),
   if one has been posted, or build it yourself (see below).
2. Extract it to its own folder. Don't extract it over a Retribution install.
3. Run `retribution_main.exe`.

Resolution uses the same save and settings locations as Retribution, so **back up your saves before
you try it**. Retribution campaigns open in Resolution. Campaigns saved in Resolution are not
guaranteed to open in Retribution.

## Running from source

You need Python 3.11, Node.js (for the map client) and Git.

```powershell
git clone -b Resolution https://github.com/AbhayPratapSingh2607/dcs-resolution.git
cd dcs-resolution
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Build the map client. Rebuild it whenever you switch branches.
cd client
npm ci
npm run build
cd ..

$env:PYTHONPATH = "."
python -m qt_ui.main
```

Without `PYTHONPATH`, `python qt_ui/main.py` stops with "No module named 'game'".

## Building the standalone executable

Build the map client first (see above), then run:

```powershell
.venv\Scripts\activate
$env:PYTHONPATH = ".;./pydcs"
pyinstaller pyinstaller.spec
Copy-Item .\changelog.md .\dist\dcs-retribution\
```

The finished build is in `dist\dcs-retribution`. Copy that folder wherever you want to install it.

## Branches

| Branch | Contents |
|---|---|
| `Resolution` | The combined build, and the repository's default branch |
| `combat-resolution` | The living war: the six hour turn, the commanders, the combat model, intelligence, the opening, fire missions, the bubble, your seat and the Rescue King. It contains everything in `Resolution`. |
| `CSAR` | Turn-based CSAR, also Retribution PR #929 |
| `dynamic-farp` | Dynamic FARPs |
| `onstation-flights` | The On Station start type |
| `airwing-presets` | Air wing presets |
| `loadout-screen-improvements` | Loadout editor changes |
| `superhornet-v2.4.6.260725.RC3-support`, `superhornet-2.4.6-payload-keys` | Super Hornet fixes |
| `uh60l-armed-support` | UH-60L Armed Blackhawk |
| `aewc-navmesh-fix` | AEW&C orbit fix, offered upstream |
| `dev` | Follows Retribution's `dev` branch |

Changes are made on the feature branches, which are then merged into `Resolution`. That way each
feature can be offered upstream on its own.

To run the living war before it is merged into `Resolution`, clone `combat-resolution` instead:

```powershell
git clone -b combat-resolution https://github.com/AbhayPratapSingh2607/dcs-resolution.git
```
