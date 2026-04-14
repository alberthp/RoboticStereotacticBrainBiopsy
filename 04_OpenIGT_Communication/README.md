# 04 — OpenIGTLink Communication

Real-time communication bridge between 3D Slicer and Unity.

## Overview
OpenIGTLink is an open network protocol for image-guided therapy.
It allows streaming of transforms, images, and point clouds between applications.

## Setup

### Slicer side
1. Install SlicerOpenIGTLink extension
2. Modules → OpenIGTLink IF
3. Create new connector → Server → Port 18944
4. Activate connector

### Unity side
1. Import OpenIGTLink Unity package
2. Add OpenIGTLinkConnector component to a GameObject
3. Set host: 127.0.0.1, port: 18944
4. Connect

## Data Types Supported
- TRANSFORM — tracked probe position (4×4 matrix)
- POINT — fiducial coordinates
- IMAGE — MRI/CT slice streaming
- STRING — state synchronisation messages

## Scripts
- `slicer_sender.py` — sends tracked tool transforms from Slicer
- `unity_receiver.cs` — receives and applies transforms in Unity
