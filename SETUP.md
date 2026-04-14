# Setup Guide

## Required Software

### 1 — 3D Slicer
- Download from https://download.slicer.org/
- Version ≥ 5.8 (stable)
- After install, open Extension Manager and install:
  - **SlicerModalityConverter** (Image Synthesis category)
  - **SlicerOpenIGTLink** (IGT category)
  - **HDBrain** (Segmentation category)
  - **SurfaceWrapSolidify** (Surface Models category)
  - **SlicerIGT** (IGT category)

### 2 — Unity
- Download Unity Hub from https://unity.com/download
- Install Unity **2022.3 LTS**
- Required packages (via Package Manager):
  - OpenIGTLink for Unity
  - AR Foundation (for module 07)
  - MRTK3 (for module 07, HoloLens)

### 3 — Git
- Download from https://git-scm.com/

## Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/RoboticStereotacticBrainBiopsy.git
```

## Sample Data

All modules use MRBrainTumor1, available directly in Slicer:
`File → Download Sample Data → MRBrainTumor1`
