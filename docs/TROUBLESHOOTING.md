# Troubleshooting and recovery

[← Back to the setup guide](../README.md)

Run diagnostics from the repository folder:

```sh
./cortex-control doctor
```

After installation, `~/.local/bin/cortex-control doctor` runs the same checks.
Diagnostics inspect prerequisites, configuration, selected file hashes, visible
HID ownership and access permissions. They do not prove Vulkan rendering, USB
communication, or save correctness. Review personal paths and device details
before sharing reports or logs.

## Common problems

| Symptom | What to check |
| --- | --- |
| **No Proton found** | Install Proton Experimental through Steam's Tools library, or pass `--runtime /path/to/Proton`. Other runtime layouts are not assumed compatible. |
| **Missing host tools** | `doctor` names missing prerequisites. The host needs Python 3.11+, `bwrap`, `lsof`, `cp`, `desktop-file-validate`, and `7z` or `7zz` for extraction. The installer does not automatically layer packages onto Bazzite. |
| **No QC permission** | Use your logged-in local desktop session. Do not run the app as root or apply blanket USB permissions. |
| **QC in use** | Finish the other editor session. The launcher checks visible ownership and acquires CorTux's cooperative HID lock. |
| **QC connected after startup** | Close the app normally and relaunch after connecting. The sandbox exposes the HID node chosen at startup; hotplug recovery is unqualified. |
| **Running session, no window** | The app may still be starting. Check its window and `doctor`; no process is automatically killed or reset. `wmctrl` is needed to focus an existing window. |
| **Missing menu entry** | Run `./cortex-control repair` from the checkout. Settings and application files are retained. |
| **Damaged app or runtime** | Run `reinstall --installer /path/to/installer.exe --runtime /path/to/Proton` with good input copies. Existing copies remain available. |
| **Startup failed** | Inspect `last-run.log` in the active state directory reported by `doctor`. Review it for personal information before sharing. |

The desktop must provide working host Vulkan and an X11 display or XWayland.
KDE's `kdialog` supplies the installer picker and graphical messages. Installation
uses a user-local prefix; no Python packages, shared Wine prefix or system-driver
installation is needed.

An earlier startup hang involved Wine audio discovery. The launcher disables
only its own Wine audio backends. Linux audio/MIDI and other applications retain
their existing drivers and settings.

## Storage and recovery

| Item | Location |
| --- | --- |
| Installation | `${XDG_DATA_HOME:-~/.local/share}/cortex-control-linux` |
| Command launcher | `~/.local/bin/cortex-control` |
| Imports and exports | `~/Documents/Cortex Control`, or the retained installation's configured folder |
| Active configuration | `install.json` inside the installation |
| New app/runtime/prefix bundles | `installs/<id>` inside the installation |
| Integration snapshots and previous configurations | `backups/` inside the installation |

Install/reinstall prepares a separate bundle containing the app, runtime and
prefix. The active configuration is replaced after preparation and desktop
validation succeed. Existing bundles and legacy layouts are retained; previous
prefixes and documents are not automatically deleted. Keep enough space for both
old and new copies.

An interrupted preparation is not reused: retry creates a fresh staging copy.
An interruption during desktop integration may require `repair`. For a failed
reinstall, the previous configuration stays active unless the final commit
completed. Keep retained bundles while diagnosing a failure.

`uninstall` removes desktop integration and retains application files, settings
and backups. Use `repair` from the checkout to restore the menu. `install` refuses
to replace an existing installation; use `reinstall` for that purpose.

Installation recovery is **not a backup of presets on the physical QC**.
Firmware/reset workflows remain outside this project's scope.

## Older commands

`run.sh`, `scripts/setup.py` and `scripts/launch.py` delegate to the unified
implementation. Use the documented `cortex-control` commands for new setups.

[Compatibility record](../COMPATIBILITY.md) · [Optional audio](../AUDIO.md) ·
[Report an issue](https://github.com/Mordeton/cortex-control-linux/issues/new?template=bug_report.md)
