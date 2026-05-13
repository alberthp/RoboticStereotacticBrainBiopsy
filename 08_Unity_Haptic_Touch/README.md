# 06 — Haptic Touch Device Integration

Force feedback simulation using a Touch haptic device (3D Systems).

## Hardware Required
- Touch (formerly Phantom Omni) or Touch X haptic device
- USB connection

## Setup
1. Install OpenHaptics SDK (3D Systems)
2. Install Touch device driver
3. Import haptic Unity plugin

## Features
- Force feedback on skull surface contact
- Resistance simulation when probe touches fiducial screw
- Vibration feedback on registration confirmation

## Scripts
- `HapticManager.cs` — initialises haptic device
- `HapticFeedback.cs` — defines force responses per object type
- `ProbeController.cs` — maps haptic stylus to virtual probe
