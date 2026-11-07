# Installing and building

## Installing a packaged build

1. Download a build from the [Releases page](https://github.com/AbhayPratapSingh2607/dcs-retribution/releases),
   if one has been posted, or build it yourself (see below).
2. Extract it to its own folder. Don't extract it over a Retribution install.
3. Run `retribution_main.exe`.

Resolution uses the same save and settings locations as Retribution, so **back up your saves before
you try it**. Retribution campaigns open in Resolution. Campaigns saved in Resolution are not
guaranteed to open in Retribution.

## Running from source

You need Python 3.11, Node.js (for the map client) and Git.

```powershell
git clone -b Resolution https://github.com/AbhayPratapSingh2607/dcs-retribution.git
cd dcs-retribution
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Build the map client. Rebuild it whenever you switch branches.
cd client
npm ci
npm run build
cd ..

python qt_ui/main.py
```

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
| `Resolution` | The combined build, with every feature below merged in |
| `CSAR` | Turn-based CSAR, also Retribution PR #929 |
| `dynamic-farp` | Dynamic FARPs |
| `loadout-screen-improvements` | Loadout editor changes |
| `superhornet-v2.4.6.260725.RC3-support`, `superhornet-2.4.6-payload-keys` | Super Hornet fixes |
| `uh60l-armed-support` | UH-60L Armed Blackhawk |
| `dev` | Follows Retribution's `dev` branch |

Changes are made on the feature branches, which are then merged into `Resolution`. That way each
feature can be offered upstream on its own.
