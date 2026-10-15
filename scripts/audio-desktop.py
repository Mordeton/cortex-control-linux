#!/usr/bin/env python3
"""Keep a selectable QC USB 1/2 stereo endpoint across login and reconnect."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

NAME = 'qc_headphones'
ROOT = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'cortex-control-linux'
UNIT = Path.home() / '.config/systemd/user/quad-cortex-headphones.service'


def pactl(*args):
    return subprocess.check_output(['pactl', *args], text=True).strip()


def items(kind):
    return json.loads(pactl('-f', 'json', 'list', kind))


def ensure():
    sinks = items('sinks')
    masters = [s for s in sinks if s['name'].startswith('alsa_output.usb-Neural_DSP_Quad_Cortex-')]
    if len(masters) != 1:
        return False
    if not {'front-left', 'front-right'}.issubset(masters[0]['channel_map'].split(',')):
        return False
    if not any(s['name'] == NAME for s in sinks):
        pactl('load-module', 'module-remap-sink', 'sink_name=' + NAME,
              'master=' + masters[0]['name'], 'channels=2', 'channel_map=front-left,front-right',
              'master_channel_map=front-left,front-right', 'rate=48000', 'remix=no',
              'sink_properties=device.description="Quad Cortex Headphones (USB 1-2)"')
    return True


def watch():
    # Subscribe before checking, so a hotplug during initialization is not missed.
    with subprocess.Popen(['pactl', 'subscribe'], stdout=subprocess.PIPE, text=True, bufsize=1) as events:
        ensure()
        for event in events.stdout:
            if ' on sink #' in event or ' on module #' in event:
                ensure()
    raise SystemExit(1)  # systemd restarts this if the audio server reconnects.


def install():
    script = ROOT / 'scripts/audio-desktop.py'
    script.parent.mkdir(parents=True, exist_ok=True)
    if Path(__file__).resolve() != script.resolve():
        shutil.copy2(__file__, script)
    UNIT.parent.mkdir(parents=True, exist_ok=True)
    UNIT.write_text('[Unit]\nDescription=Quad Cortex stereo headphone endpoint\nAfter=pipewire-pulse.service\n'
                    '\n[Service]\nExecStart=/usr/bin/python3 "' + str(script) + '" watch\nRestart=on-failure\nRestartSec=3\n'
                    '\n[Install]\nWantedBy=default.target\n')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', UNIT.name], check=True)
    print('QC stereo endpoint enabled at login and on reconnect. Select it in KDE Audio when wanted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'watch', 'select', 'remove'])
    action = parser.parse_args().action
    if action == 'install':
        install()
    elif action == 'watch':
        watch()
    elif action == 'select':
        if not ensure():
            raise SystemExit('Connect one Quad Cortex with its USB audio profile enabled.')
        pactl('set-default-sink', NAME)
    else:
        subprocess.run(['systemctl', '--user', 'disable', '--now', UNIT.name], check=True)
        UNIT.unlink(missing_ok=True)
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        print('Login helper removed. The current endpoint remains until logout or audio restart.')


if __name__ == '__main__':
    main()
