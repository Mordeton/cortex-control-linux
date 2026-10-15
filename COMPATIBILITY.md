# Compatibility and qualification

This is an unofficial wrapper around the original Windows application. It does
not establish official Neural DSP support for Linux.

| Component | Recorded configuration |
| --- | --- |
| Desktop | x86_64 Bazzite, KDE/Wayland with XWayland |
| Graphics | NVIDIA RTX 2080 SUPER; DXVK |
| Cortex Control | 4.1.0 |
| Quad Cortex firmware | CorOS 4.1.1 |
| Proton runtime | `1791480010 experimental-11.0-20261008-x86_64` |
| Network | Blocked |

## Previously observed on hardware, 2026-10-14 to 2026-10-15

- Original application rendered and connected to a physical QC.
- The existing grid and unsaved-state indicator appeared in the UI.
- Normal window close released the HID interface.
- A second desktop launch activated the existing window.
- Linux USB audio and MIDI remained available alongside editor control.
- Disabling the launcher's Wine audio backends resolved an observed startup hang.

These observations come from the earlier local desktop launcher. Automated
installer tests do not extend those hardware qualifications to every new runtime,
GPU, host configuration or device workflow.

## Installer validation, 2026-10-15

- 24 offline regression tests cover install/reinstall failures, preserved settings,
  legacy layouts, repair after removal, runtime discovery, diagnostics and ownership locks.
- An isolated local test using the retained verified EXE and the runtime above
  completed real Wine prefix initialization, reinstall with a preserved settings
  marker, removal/repair of desktop integration, and desktop-file validation.
- The isolated test exposed no QC interface and made no device changes. It did
  not re-test Windows bootstrapper extraction, application rendering or Save.

## Still unqualified

- Full editing and Save/reload correctness, import/export and backup/restore.
- Long sessions, suspend/resume and USB reconnection.
- Other GPUs, distributions, desktops, Cortex Control versions and Proton builds.
- Cloud, updates, firmware operations and factory reset.
- Optional headphone helper across actual reboot and physical reconnect.

The launcher preserves the exact 4.1.0 application hash check. The installer
extraction offsets are specific to this exact Windows bootstrapper:

- Installer SHA-256: `c03942a0631afd195d3d70febf91384bf39cb7101014146f26f5ba65fd73228c`
- Application SHA-256: `9be548fb6cbd2e8c80715015c2a2f0f248c9b01a7165004e2b017ffe2b14e65a`

A different Proton build with the required files may be selected, but is reported
as untested. Pinning a private copy prevents Steam updates from changing that
installation's selected runtime.

Official references: [Cortex Control](https://neuraldsp.com/cortex-control),
[downloads](https://neuraldsp.com/downloads),
[QC manual](https://neuraldsp.com/manual/quad-cortex).
Runtime projects: [Proton](https://github.com/ValveSoftware/Proton),
[Wine](https://www.winehq.org/), [DXVK](https://github.com/doitsujin/dxvk).
