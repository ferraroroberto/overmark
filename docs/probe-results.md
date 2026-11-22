# Probe results: PySide6 overlay

The step-0 probe decides whether the drawing surface stays in Python with PySide6 or moves to a small Rust renderer. This page records what was measured, how, and what is still open. The probe scripts were throwaway and are not in the repository; the method below is enough to rebuild them.

**Verdict: stay on PySide6.** Everything that could be measured here points to PySide6 being fast enough. The app's own cost per stroke update is about 0.1 ms, and it never fell behind a 250 Hz input stream. The on-screen input-to-photon figure and the OBS checks still need the owner's run (see [Still unmeasured](#still-unmeasured)). If that run misses the pass bar, this verdict is reopened.

## Pass bar

From the probe issue: input to photon of two frames or less (about 33 ms at 60 Hz), and no dropped frames during a 10-second scribble on each monitor.

## Test machine

- Windows 11, one 1080p monitor at 60 Hz and 100 % scale, a desktop discrete GPU.
- PySide6 6.12 on Python 3.14.
- No pen or touch digitizer attached (the system reports no digitizer).
- No 4K display and no mixed-DPI pair available.
- The desktop was **locked** for the whole run, with the owner away. The lock screen sits above every window, so the overlay never reached the display and synthetic `SendInput` events went to the lock screen. This limits what could be measured; see below.

## Method

- **Overlay.** One frameless, top-most, per-pixel-alpha window per monitor (`Qt.Tool`, `WA_TranslucentBackground`, extended style `WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW`). Each window keeps an ARGB backing image at the monitor's native resolution and draws a stroke segment into it on every mouse move. It then invalidates only the segment's dirty rectangle, so each repaint copies just that rectangle. The backing image is filled with alpha 1, not 0, so the window stays hit-testable in draw mode while remaining invisible.
- **Global hotkey.** `RegisterHotKey(Ctrl+Alt+D)` through a Qt native event filter toggles `WS_EX_TRANSPARENT` (click-through) at runtime. Registration succeeded. The toggle itself was not pressed, because keyboard input also goes to the lock screen.
- **Toolbar.** A separate small top-most window with `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)`. `GetWindowDisplayAffinity` reads back `0x11`.
- **Timing.** The app logs, using the shared performance counter: the time each mouse-move handler starts, and the start and end of each Qt `UpdateRequest`, which covers the paint plus the layered-window flush.
- **Input.** Strokes were driven by posted `WM_LBUTTONDOWN` / `WM_MOUSEMOVE` messages with button state, sent straight to the overlay window. This skips only the OS hit-test and raw-input stage, which `SendInput` would have exercised on an unlocked desktop.
  - Latency trials: 100 single 14 px steps with random vsync phase.
  - Scribble: 10 s at 250 Hz on a drifting circle, with the hue cycling so every update changes pixels.
- **Capture.** Windows Graphics Capture (WGC) of the overlay window itself. WGC still captures a window that is covered, and each frame carries the time the compositor composed it. The same API was used for the capture-hiding checks. A desktop-duplication grab was also tried; it only sees the composed desktop, which here was the lock screen.

## Results

Two runs agree to within a few percent. The numbers are from the second run.

| Measurement (1080p, 60 Hz, mouse-equivalent input) | Median | p95 | Max |
|---|---|---|---|
| Move handler start to paint and flush done | 0.11 ms | 0.30 ms | 2.33 ms |
| One `UpdateRequest` (dirty-rect paint plus layered flush) | 0.08 ms | 0.15 ms | 1.36 ms |
| Full-window repaint and flush (worst case, for example a whole-screen fade) | 0.59 ms | 0.78 ms | 1.41 ms |

- **Keeping up with input.** In the 10-second scribble, 2,501 inputs produced 2,497 repaints. The longest gap between repaints was 9.9 ms, and no gap exceeded 1.5 refresh periods (25 ms). The app side drops nothing at 250 Hz.
- **4K estimate, not measured.** A full-window repaint scales with pixel count, so about 2.4 ms at 4K. Dirty-rect strokes cost the same at any resolution.
- **Lock-screen artifact.** While the session is locked, the compositor composes the covered overlay only every 266.7 ms (every 16th refresh). Input-to-composed-frame therefore read about 200 ms median, and only 38 composed frames appeared in the 10-second scribble. Both numbers measure that throttle, not the app, and are not used for the verdict.

**Why the verdict holds.** At 60 Hz the app spends about 0.1 ms of a 16.7 ms frame, so the rest of the 33 ms budget is the compositor and scan-out. A Rust DirectComposition renderer would go through the same compositor and the same scan-out. It could only save the app-side fraction of a millisecond measured here, plus the layered-window copy, which the full-window figure shows is under 1 ms at 1080p.

## Capture-hiding

Checked with Windows Graphics Capture window captures, one of the capture methods OBS Window Capture offers:

| Captured window | Frames delivered | Ink visible | Toolbar visible |
|---|---|---|---|
| Capture-excluded toolbar | none (the capture yields nothing) | n/a | no |
| Ink overlay | yes | yes (the full ink band) | no |
| Another application's window, under the ink | yes | no (only its own content) | no |

A window capture of another application never contains the ink, so the README's statement holds: OBS **Window Capture** of an app shows no ink. A display (monitor) capture could not be checked, because the composed desktop was the lock screen. The OBS **Display Capture** result is therefore open (below).

## Pen

Not measured: no pen or touch digitizer is attached to the test machine. Whether `QTabletEvent` delivers pressure, tilt, and the barrel and eraser buttons is still open.

## Still unmeasured

These need the owner's monitors, pen and OBS setup, on an unlocked desktop. Each step is short.

1. **Input to photon, per monitor.**
   - Rebuild the overlay above and drive it with `SendInput` (absolute mouse moves with the left button held) on an unlocked desktop.
   - Time each move against desktop-duplication frames, or WGC monitor-capture frames: the first frame in which the target pixel shows ink.
   - Add one refresh period for scan-out to get input to photon.
   - Repeat on each monitor, including a 4K monitor and a mixed-DPI pair if available.
   - Pass: median and p95 at or under about 33 ms at 60 Hz.
2. **Dropped frames on screen.** Run the same 10-second 250 Hz scribble and count gaps between composed frames longer than 1.5 refresh periods. Pass: none.
3. **OBS Display Capture.**
   - With the overlay showing ink and the excluded toolbar beside it, add a Display Capture source in a new scene. Do not change existing scenes.
   - Confirm the ink is visible and the toolbar is not.
4. **OBS Window Capture.** Capture another application's window that has ink drawn over it. Expected: no ink.
5. **Pen.**
   - Log `QTabletEvent` pressure, `xTilt` / `yTilt`, the buttons and the pointer type while drawing with a real pen.
   - Check that the barrel button and the eraser end arrive.
   - Note any quirks of Qt's Windows pointer path, such as mouse events synthesised alongside tablet events.
6. **One surface across monitors.** With one overlay window per monitor, draw a stroke across a monitor boundary and confirm it reads as one continuous surface.
