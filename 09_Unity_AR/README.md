# 07 — Augmented Reality Integration

AR overlay of surgical plan onto physical skull phantom.

## Hardware Options
- Microsoft HoloLens 2 (MRTK3)
- Meta Quest 3 (AR passthrough)
- Any OpenXR-compatible headset

## Setup
1. Install Mixed Reality Toolkit (MRTK3) via Package Manager
2. Install AR Foundation
3. Configure XR Plugin Management for target device

## Features
- Fiducial marker locations overlaid on physical skull
- Planned insertion trajectory visualised as AR line
- Tumour location shown as translucent sphere
- Real-time registration error display

## Scripts
- `AROverlay.cs` — manages AR anchor placement
- `TrajectoryVisualiser.cs` — renders insertion path in AR
- `RegistrationDisplay.cs` — shows FLE/TRE in AR HUD
