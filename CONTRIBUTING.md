# Contributing

Keep changes focused on installation, launch compatibility and diagnostics.
Never commit installers, DLLs, prefixes, presets, device traces or personal logs.
The repository does not distribute the Windows application or Proton runtime.

Run `python3 -m unittest discover -s tests -v` before proposing a change.
Tests must work offline without a QC or proprietary binaries. Distinguish
synthetic tests, disconnected Wine tests, and actual hardware qualification.

For reports, include the Bazzite/KDE version, GPU/driver, Cortex Control version,
Proton version and a redacted `doctor` report. Describe the expected result and
what happened. Review logs for names, paths and device data before sharing.

Preserve the exclusive session/HID locks, offline default, private prefix, and
stop-on-competing-ownership behavior. Do not add automatic device resets,
firmware updates, blanket permission changes or process killing. Do not test
Save or preset changes against someone else's unsaved device state.

For a new app version, add separately reviewed extraction metadata and evidence;
do not disable the executable hash check. Keep an explicit compatibility matrix.
