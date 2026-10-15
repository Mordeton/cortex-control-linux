# Optional headphone output

The editor does not need Wine audio drivers. Linux handles the QC's USB audio
and MIDI independently. This optional helper creates a selectable stereo endpoint
for USB playback channels 1/2; it does not install drivers or change QC presets.

From this repository, with PipeWire's PulseAudio compatibility service and `pactl`:

```sh
python3 scripts/audio-desktop.py install
```

Select **Quad Cortex Headphones (USB 1-2)** in KDE Audio, or explicitly select it:

```sh
python3 scripts/audio-desktop.py select
```

The user service follows audio-server events and does not continually override
your selected output or volume. USB 1/2 playback was heard on the original test
machine; actual login/reconnect behavior remains unqualified.

Remove the service:

```sh
python3 scripts/audio-desktop.py remove
```

The currently created endpoint remains until logout or audio-server restart.
Rocksmith, ASIO bridges and preset automation are separate projects and are not
configured by this installer.
