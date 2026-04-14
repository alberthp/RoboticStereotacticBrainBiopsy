# Robotic Stereotactic Brain Biopsy
### An Open-Source Educational Simulation Pipeline

[![3D Slicer](https://img.shields.io/badge/3D_Slicer-5.8+-blue)](https://download.slicer.org/)
[![Unity](https://img.shields.io/badge/Unity-2022.3+-black)](https://unity.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![OpenIGTLink](https://img.shields.io/badge/OpenIGTLink-3.0-orange)](http://openigtlink.org/)

---

## Overview

This repository contains a complete educational pipeline for simulating a **robotic stereotactic brain biopsy** procedure. It covers the full workflow from pre-operative medical image processing in 3D Slicer to intra-operative simulation in Unity, including patient-to-image registration, surgical planning, robotic arm control, and optional haptic and augmented reality feedback.

The pipeline is designed for **bioengineering and medical robotics students** and mirrors the clinical workflow used in real stereotactic neurosurgery.

---

## Clinical Context

In stereotactic brain biopsy:

1. **Pre-operative**: Bone-anchored fiducial markers are implanted in the patient's skull. MRI and/or CT scans are acquired with the markers in place.
2. **Planning**: A neurosurgeon identifies the target (e.g. brain tumour centroid) and plans the optimal insertion trajectory.
3. **Registration**: In the operating room, a tracked probe touches each fiducial marker. The resulting point cloud is aligned with the pre-operative imaging to establish a common coordinate system.
4. **Execution**: A robotic arm (e.g. Franka Emika) guides a biopsy needle along the planned trajectory with sub-millimetre accuracy.

This repository simulates each of these phases digitally.

---

## Full Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        PRE-OPERATIVE                            │
│                                                                 │
│  MRBrainTumor1 (T1w MRI)                                       │
│       │                                                         │
│       ├─► 01_MRI_to_CT ──► Synthetic CT (FedSynthCT)           │
│       │                                                         │
│       ├─► 02_Segmentation ──► Skull mesh (OBJ/STL)             │
│       │                       Brain segmentation               │
│       │                       Tumour segmentation              │
│       │                                                         │
│       └─► 03_FiducialScrews ──► MRI with simulated screws      │
│                                 Ground truth coordinates        │
└─────────────────────────────────────────────────────────────────┘
                              │
                    04_OpenIGT_Communication
                    (Slicer ↔ Unity bridge)
                              │
┌─────────────────────────────────────────────────────────────────┐
│                        INTRA-OPERATIVE                          │
│                                                                 │
│  05_Unity_Core_Simulator                                        │
│       │                                                         │
│       ├─► Load skull mesh + brain + tumour                     │
│       ├─► Student places probe on fiducials → point cloud      │
│       ├─► SVD Registration (virtual ↔ physical)                │
│       ├─► Plan insertion trajectory                             │
│       └─► Robotic arm guidance simulation                       │
│                                                                 │
│  06_Unity_Haptic_Touch ──► Force feedback on probe contact     │
│                                                                 │
│  07_Unity_AR ──► AR overlay on patient phantom                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
RoboticStereotacticBrainBiopsy/
│
├── README.md                        ← You are here
├── SETUP.md                         ← Installation guide for all software
├── LICENSE
│
├── 01_Slicer_MRI_to_CT/            ← MRI → Synthetic CT conversion
│   ├── README.md
│   └── scripts/
│
├── 02_Slicer_Segmentation/         ← Skull, brain, tumour segmentation
│   ├── README.md
│   └── scripts/
│
├── 03_Slicer_FiducialScrews/       ← Simulated bone-anchored screws
│   ├── README.md
│   └── scripts/
│
├── 04_OpenIGT_Communication/       ← Slicer ↔ Unity real-time bridge
│   ├── README.md
│   └── scripts/
│
├── 05_Unity_Core_Simulator/        ← Main surgical simulation
│   ├── README.md
│   └── Assets/
│
├── 06_Unity_Haptic_Touch/          ← Touch haptic device integration
│   ├── README.md
│   └── Assets/
│
└── 07_Unity_AR/                    ← AR glasses integration
    ├── README.md
    └── Assets/
```

---

## Modules

### [01 — MRI to CT Conversion](01_Slicer_MRI_to_CT/README.md)
Converts T1-weighted MRI brain scans to synthetic CT using the **FedSynthCT-Brain** federated learning model integrated in the SlicerModalityConverter extension. Synthetic CT provides Hounsfield Unit values needed for bone segmentation and radiotherapy dose planning.

**Key tools:** 3D Slicer, SlicerModalityConverter, FedSynthCT Fu/Li models

---

### [02 — Segmentation and 3D Reconstruction](02_Slicer_Segmentation/README.md)
Segments anatomical structures from the synthetic CT and MRI:
- **Skull** — threshold-based segmentation with manual cleanup
- **Brain** — HDBrain extension (deep learning)
- **Tumour** — semi-automatic segmentation with statistics

Exports 3D surface meshes (OBJ/STL) for Unity import.

**Key tools:** 3D Slicer Segment Editor, HDBrain, SurfaceWrapSolidify

---

### [03 — Fiducial Screw Simulation](03_Slicer_FiducialScrews/README.md)
Simulates bone-anchored fiducial screws by burning bright cylindrical signals directly into the MRI voxel array. Produces a realistic pre-operative MRI dataset where students must identify and localise 9 screws distributed in a 3×3 grid on the parietal skull surface.

**Key output:** `MRI_WithScrews.nrrd` (student dataset) + `ScrewFiducials_GroundTruth.fcsv` (teacher answer key)

**Key tools:** 3D Slicer Python Interactor, NumPy, VTK

---

### [04 — OpenIGTLink Communication](04_OpenIGT_Communication/README.md)
Establishes real-time bidirectional communication between 3D Slicer and Unity using the **OpenIGTLink** protocol. Enables live streaming of:
- Transform matrices (tracked probe position)
- Point clouds (fiducial coordinates)
- Volume data (MRI/CT slices)
- String messages (state synchronisation)

**Key tools:** SlicerOpenIGTLink extension, OpenIGTLink Unity plugin

---

### [05 — Unity Core Simulator](05_Unity_Core_Simulator/README.md)
The main surgical simulation in Unity:
- Import and display skull mesh, brain volume, tumour model
- Interactive probe placement on fiducial markers
- **SVD-based rigid registration** (virtual point cloud → physical point cloud)
- Insertion trajectory planning and visualisation
- Robotic arm (Franka Emika) simulation

**Key tools:** Unity 2022.3+, C#, Math.NET Numerics (SVD)

---

### [06 — Haptic Touch Device](06_Unity_Haptic_Touch/README.md)
Integrates a **Touch haptic device** (3D Systems) with the Unity simulator to provide force feedback when the virtual probe contacts the skull surface or fiducial markers. Simulates the tactile sensation of the registration procedure.

**Key tools:** Unity, OpenHaptics SDK, Touch device driver

---

### [07 — Augmented Reality](07_Unity_AR/README.md)
Projects the surgical plan (tumour location, insertion trajectory, fiducial grid) as an AR overlay onto a physical skull phantom using AR glasses (e.g. Microsoft HoloLens 2 or Meta Quest 3). Bridges virtual planning and physical execution.

**Key tools:** Unity, MRTK (Mixed Reality Toolkit), AR Foundation

---

## Getting Started

### Prerequisites

| Software | Version | Purpose |
|---|---|---|
| [3D Slicer](https://download.slicer.org/) | ≥ 5.8 | Medical image processing |
| [SlicerModalityConverter](https://github.com/ciroraggio/SlicerModalityConverter) | Latest | MRI → CT conversion |
| [Unity](https://unity.com/download) | 2022.3 LTS | Simulation environment |
| [OpenIGTLink](http://openigtlink.org/) | 3.0 | Slicer ↔ Unity communication |
| Python | 3.9+ (bundled with Slicer) | Scripting |

### Quick Start

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/RoboticStereotacticBrainBiopsy.git
cd RoboticStereotacticBrainBiopsy
```

Then follow the modules in order:

1. Start with **[SETUP.md](SETUP.md)** to install all required software
2. Follow **[01_Slicer_MRI_to_CT](01_Slicer_MRI_to_CT/README.md)** to generate the synthetic CT
3. Follow **[02_Slicer_Segmentation](02_Slicer_Segmentation/README.md)** to segment anatomical structures
4. Follow **[03_Slicer_FiducialScrews](03_Slicer_FiducialScrews/README.md)** to generate the simulated screw dataset
5. Follow **[04_OpenIGT_Communication](04_OpenIGT_Communication/README.md)** to set up the Slicer–Unity bridge
6. Follow **[05_Unity_Core_Simulator](05_Unity_Core_Simulator/README.md)** to run the surgical simulation

Modules 06 and 07 are optional extensions requiring additional hardware.

---

## Sample Data

All modules use the **MRBrainTumor1** sample dataset available directly in 3D Slicer:

```
3D Slicer → File → Download Sample Data → MRBrainTumor1
```

| Property | Value |
|---|---|
| Modality | T1-weighted MRI |
| Dimensions | 256 × 256 × 112 voxels |
| Spacing | 0.938 × 0.938 × 1.4 mm |
| Coverage (S) | -77.7 to +79.1 mm |

---

## Educational Outcomes

After completing the full pipeline, students will be able to:

- Explain why CT is preferred over MRI for rigid tissue imaging and how synthetic CT addresses this
- Perform threshold-based and deep-learning skull/brain segmentation in 3D Slicer
- Understand the role of bone-anchored fiducial markers in surgical registration
- Implement SVD-based point-to-point rigid registration in Unity/C#
- Measure and interpret Fiducial Localisation Error (FLE) and Target Registration Error (TRE)
- Describe the OpenIGTLink protocol and its role in surgical navigation systems
- Integrate haptic feedback and AR visualisation into a surgical simulation

---

## Contributing

Contributions are welcome. Please open an issue first to discuss proposed changes.

For new module contributions, follow the existing README structure and include:
- Purpose and clinical context
- Step-by-step instructions with code
- Expected outputs with example values
- Screenshots (where applicable)

---

## Citation

If you use this repository in academic work, please cite:

> [Author], *Robotic Stereotactic Brain Biopsy — An Open-Source Educational Simulation Pipeline*, GitHub, 2025. https://github.com/YOUR_USERNAME/RoboticStereotacticBrainBiopsy

For the MRI-to-CT conversion component:

> C.B. Raggio et al., *FedSynthCT-Brain: A federated learning framework for multi-institutional brain MRI-to-CT synthesis*, Computers in Biology and Medicine, Vol. 192, 2025. https://doi.org/10.1016/j.compbiomed.2025.110160

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

The FedSynthCT models are licensed for **research purposes only**. See [SlicerModalityConverter MODEL_LICENSE](https://github.com/ciroraggio/SlicerModalityConverter/blob/main/MODEL_LICENSE) for details.

---

## Acknowledgements

- [SlicerModalityConverter](https://github.com/ciroraggio/SlicerModalityConverter) — C.B. Raggio, P. Zaffino, M.F. Spadea
- [3D Slicer](https://www.slicer.org/) — Fedorov et al., Magn Reson Imaging, 2012
- [OpenIGTLink](http://openigtlink.org/) — Tokuda et al., Int J Med Robot, 2009
