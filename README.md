# Cortex Control on Bazzite

[![Offline tests](https://github.com/Mordeton/cortex-control-linux/actions/workflows/tests.yml/badge.svg)](https://github.com/Mordeton/cortex-control-linux/actions/workflows/tests.yml)

An unofficial, user-local launcher for the **Windows Cortex Control 4.1.0 app**
on x86_64 Bazzite/KDE. It uses a private copy of Proton's Wine runtime and DXVK,
with direct access to the Quad Cortex HID control interface.

**Status: experimental, offline compatibility wrapper.** The original app has
rendered and connected on the tested machine. This is not a native Linux port,
a replacement editor, or a Neural DSP product. See [tested scope](COMPATIBILITY.md).

**Tested hardware: full-size Quad Cortex only.** The **Quad Cortex mini has not
been tested**; its compatibility with this launcher is unknown.

## Disclaimer

- This is an independent community project, not affiliated with or endorsed by
  Neural DSP. Cortex Control and Quad Cortex remain Neural DSP's products and
  trademarks. Obtain Cortex Control separately and follow its applicable license terms.
- This experimental wrapper is provided **as is**, without warranty, under the
  [MIT license](LICENSE). Use it at your own risk; reliable operation or protection
  against crashes, data loss or workflow disruption is not guaranteed.
- Back up important presets using a supported method before experimenting.
  Save/reload, import/export and backup/restore remain unqualified here. Retained
  installation copies are **not backups of presets on your QC**. Firmware updates
  and factory resets are outside this project's scope.

## Quick start

1. In Steam's Library, enable the **Tools** filter and install **Proton Experimental**.
2. Obtain your **Cortex Control 4.1.0 Windows installer** from
   [Neural DSP](https://neuraldsp.com/downloads). The launcher accepts only the exact
   tested installer/executable hashes. If that version is no longer offered,
   this release cannot install a newer version; do not bypass the check.
3. [Download the source ZIP](https://github.com/Mordeton/cortex-control-linux/archive/refs/heads/main.zip)
   and extract it, or clone the repository:

   ```sh
   git clone https://github.com/Mordeton/cortex-control-linux.git
   cd cortex-control-linux
   ```

   Open a terminal in the extracted/cloned folder and run as your normal desktop user:

   ```sh
   ./cortex-control doctor
   ./install.sh
   ```

   On KDE, a file picker asks for the installer. Proton is detected in Steam's
   default and additional libraries. A tested build is preferred; other builds
   receive an explicit untested-runtime notice.
4. Close other QC editor sessions and open **Cortex Control** from the application
   menu. Connect the QC before launching for hardware access.

No Python packages, system Wine prefix, system-driver installation, or `sudo`
are needed. Installation copies the runtime and can take a few minutes and several
GB. Keep sufficient free space for both the new and retained old copies when reinstalling.

For explicit input paths:

```sh
./cortex-control install \
  --installer '/path/to/Cortex Control v4.1.0.exe' \
  --runtime '/path/to/Proton - Experimental'
```

`--exe` can replace `--installer` for an already extracted executable with the
same verified hash. The app hash is also checked before each launch. `--migrate-prefix /path/to/prefix` copies an existing prefix
on first installation; its original is preserved.

## Everyday commands

Run these from the repository folder, or use `~/.local/bin/cortex-control`
after installation:

| Command | Result |
| --- | --- |
| `./cortex-control` | Launch; focus an existing window if possible |
| `./cortex-control run --disconnected` | Launch without exposing USB/HID devices |
| `./cortex-control files` | Open the import/export folder |
| `./cortex-control doctor` | Inspect installation, prerequisites and QC access without opening the HID connection |
| `./cortex-control repair` | Restore/update scripts, launcher and menu entry; preserve the app, prefix and settings |
| `./cortex-control reinstall` | Rebuild using the retained verified EXE and runtime; preserve settings in a copied prefix |
| `./cortex-control uninstall` | Remove launcher/menu integration; retain application files and personal data |

After uninstall, run `./cortex-control repair` from this checkout to restore the
menu. To repair damaged application/runtime files, use `reinstall --installer …
--runtime …` with good input copies. `install` never replaces an existing installation.
The older `run.sh`, `scripts/setup.py` and `scripts/launch.py` delegate to this
same implementation.

## Prerequisites and troubleshooting

The host needs Python 3.11+, `bwrap`, `lsof`, `cp`, `desktop-file-validate`, and
`7z` or `7zz` for installer extraction. KDE's `kdialog` enables the file picker
and error dialogs; `wmctrl` enables existing-window activation. The graphics
runtime needs functioning host Vulkan support and an X11 desktop or XWayland.

Run `doctor` first. It checks file presence, selected hashes, desktop environment,
visible HID ownership and access permissions. It does **not** prove Vulkan
rendering, USB communication, or save correctness. Missing tools are reported by
name; this project does not automatically layer packages onto Bazzite.

- **No Proton found:** install Proton Experimental through Steam or provide
  `--runtime`. Other Proton layouts are not automatically assumed compatible.
- **No QC permission:** use your logged-in local desktop session and check its
  device access. Do not run the app as root or apply blanket USB permissions.
- **QC in use:** finish the other editor session. The launcher stops on detected
  ownership and also acquires CorTux's cooperative HID lock.
- **Started without a QC / USB reconnected:** close the app normally and relaunch
  after connecting the device. The sandbox exposes the HID node chosen at startup;
  hotplug recovery is not promised.
- **Running session but no window:** it may still be starting. Check the app's
  window and `doctor`; the launcher does not automatically kill or reset it.
- **Startup failed:** inspect `last-run.log` in the active state directory listed
  by `doctor`. Logs can contain personal paths/device details; review before sharing.

An earlier startup hang involved Wine audio discovery. This launcher disables
only its own Wine audio backends. Linux audio/MIDI and other applications keep
their existing drivers and settings.

## Storage and recovery

Installation is under `${XDG_DATA_HOME:-~/.local/share}/cortex-control-linux`.
The launcher is `~/.local/bin/cortex-control`; files for import/export are under
`~/Documents/Cortex Control` (or the retained installation's configured folder).

Each install/reinstall prepares a separate `installs/<id>` bundle containing the
app, runtime and prefix. The active `install.json` is replaced only after bundle
preparation and desktop validation succeed. Existing bundles and legacy layouts
are retained. Integration snapshots and previous configurations are under
`backups/`. Nothing automatically deletes a previous prefix or your documents.
Reinstall can therefore use additional disk space.

An interrupted preparation is not reused: retry creates a fresh staging copy.
An interruption at desktop integration may require `repair`. For a failed
reinstall, the previous configuration remains active unless the final commit
completed. Do not delete retained bundles while diagnosing a failure. This is
installation recovery, not a backup of presets stored on the physical QC.

## Network and optional audio

Networking is blocked: **Cloud login, downloads and updates are unavailable**.
The UI still contains the original app's controls; this wrapper is not a device
write filter. Only perform device operations you intend. Firmware/reset workflows
are outside this project's scope.

Optional QC USB 1/2 headphone routing is described in [AUDIO.md](AUDIO.md).
It is independent of the editor and is never installed automatically.

## Development and contributions

```sh
python3 -m unittest discover -s tests -v
```

The automated tests use synthetic files and mocked Wine/hardware operations.
They do not need proprietary software or a connected QC. See
[CONTRIBUTING.md](CONTRIBUTING.md) for issue reports and compatibility evidence.

Only the original wrapper scripts and documentation are distributed under the
[MIT license](LICENSE). Obtain the proprietary application separately; it and
Wine/Proton/DXVK retain their own licenses. See [credits](CREDITS.md).
