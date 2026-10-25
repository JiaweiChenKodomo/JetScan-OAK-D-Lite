# Browser interface

## Existing Nano installation

Open **http://10.0.0.4:8080** in a browser on the same LAN. The server is configured
to start at boot as `jw`, using the existing installation at
`/home/jw/jetscan-oak-20261024-230914` and its `scans/` directory.

1. Click **Start preview** to open the OAK-D Lite. Color and aligned depth update
   side by side. Browser camera permissions are not needed: the camera is attached
   to the Nano, not your PC.
2. Set a frame limit, then click **Start capture**. Move the camera slowly while
   the scene stays still. **Stop & save** finishes the recording at any time; the
   frame limit also stops it automatically. Closing the browser does not stop a
   recording; the limit still applies. Saved frames are checkpointed individually.
3. Select the recording and switch to **Replay recording**. Use Play/Pause or the
   frame slider to inspect the recorded RGB and depth sequence. Replay runs at
   about four frames per second for inspection, not at original acquisition speed.
4. Click **Reconstruct selected**. Capture must be stopped first. The camera is
   released, and reconstruction runs offline on the Nano. Progress appears in the
   processing log. Capture and reconstruction are mutually exclusive.
5. When complete, the model opens automatically. Drag to orbit, scroll to zoom,
   and right-drag to pan. Choose surface mesh or point cloud; **Fit** recenters it.
   Use the download links to save PLY, OBJ or the alignment preview to your PC.

The 3D viewer runs on the viewing computer. Three.js and its controls/PLY loader
are included locally, so using the interface needs no internet connection. The
browser needs WebGL for interactive 3D; exports remain downloadable without it.
This is a trusted-LAN interface without user accounts; people able to reach port
8080 can control capture and download scans. Do not forward this port to the internet.

## Install the GUI on another Nano

First complete the base installation in README.md. In that installation folder:

```bash
source .venv/bin/activate
export OPENBLAS_CORETYPE=ARMV8
python -m unittest discover -s tests -v
bash install-web-user.sh
```

The installer preserves existing crontab entries, adds one marked `@reboot` entry,
and starts the server immediately. It needs no sudo. A process lock prevents boot
and manual starts from opening duplicate servers. Cron must be enabled (it was
already active on the tested Nano). No dependency packages beyond the scanner
stack are needed. Re-running the installer updates its own marked entry.

From Windows, `deploy.ps1 -Validate -Web` installs, validates and enables the GUI.
For an existing clone, pull updates first, stop the web process while updating,
and run the installer in the same directory to keep existing scans.

For a foreground session instead of boot startup:

```bash
bash start-web.sh
```

The default address is `0.0.0.0:8080`. For a custom foreground bind:

```bash
source .venv/bin/activate
python webapp.py --host 0.0.0.0 --port 8080 --scans ./scans
```

Use **Pause preview** before accessing the camera from CLI tools. Run one web
server per camera/scan directory. The web scan list includes existing CLI scans.

## Optional systemd service

For supervised restart-on-failure instead of the user cron entry, remove only the
block between `# BEGIN JETSCAN WEB` and `# END JETSCAN WEB` with `crontab -e`, stop
the current web process, then run from your regular Nano account:

```bash
sudo bash install-web.sh
systemctl status jetscan-web.service
journalctl -u jetscan-web.service -n 60 --no-pager
```

This optional installer creates a system service that runs as the regular user.
Use one startup method. The existing Nano uses the user-cron method, so an
administrator password is not required.

## Logs and troubleshooting

- Main server log: `logs/web.log`. Reconstruction log: each scan's
  `reconstruction.log`. Request errors and tracking failures are shown in the UI.
- Inspect boot configuration with `crontab -l`; the marked block should point at
  the installation directory. The cron daemon must be running at boot.
- A camera error leaves saved frames intact. Reconnect the USB cable, check
  power, close any other DepthAI process, and click Start preview again.
- Start/stop state is shared among browsers. An operation started by one browser
  is visible in all others. Limits of 2–3000 frames and low-disk checks prevent
  unbounded recording. Failed reconstruction is reported, never labeled complete.
- No live reconstruction is performed. Real moving-camera accuracy remains
  unmeasured; start with short captures and inspect results.

## Third-party viewer assets

`web/vendor/` contains Three.js r128 (`three.min.js`, OrbitControls, PLYLoader)
from https://github.com/mrdoob/three.js/tree/r128, under the included MIT license.
