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

1. **Pre-operative — Fiducial implantation**: Bone-anchored fiducial screws are implanted in the patient's skull. MRI is acquired **with the screws already in place**.
2. **Pre-operative — Image processing**: The MRI (containing visible screw signals) is converted to synthetic CT. Anatomical structures (skull, brain, tumour) are segmented and reconstructed in 3D.
3. **Planning**: A neurosurgeon identifies the tumour centroid and plans the optimal biopsy insertion trajectory.
4. **Registration**: In the operating room, a tracked probe touches each fiducial screw. The resulting physical point cloud is aligned with the pre-operative imaging to establish a common coordinate system.
5. **Execution**: A robotic arm guides the biopsy needle along the planned trajectory with sub-millimetre accuracy.

This repository simulates each of these phases digitally, following the same order.

---

## Full Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     PRE-OPERATIVE                               │
│                                                                 │
│  MRBrainTumor1 (T1w MRI)                                       │
│       │                                                         │
│       ├─► 01_FiducialScrews ──► MRI with 9 simulated screws    │
│       │                         Ground truth coordinates        │
│       │                                                         │
│       ├─► 02_MRI_to_CT ──────► Synthetic CT (FedSynthCT)       │
│       │         (uses MRI_WithScrews as input)                  │
│       │                                                         │
│       └─► 03_Segmentation ──► Skull mesh (OBJ/STL)             │
│                                Brain segmentation               │
│                                Tumour segmentation              │
└─────────────────────────────────────────────────────────────────┘
                              │
                    04_OpenIGT_Communication
                    (Slicer ↔ Unity bridge)
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     INTRA-OPERATIVE                             │
│                                                                 │
│  05_Unity_Core_Simulator                                        │
│       │                                                         │
│       ├─► Load skull mesh + brain + tumour                     │
│       ├─► Student places probe on screws → physical point cloud │
│       ├─► SVD Registration (virtual ↔ physical)                │
│       ├─► Plan insertion trajectory to tumour                  │
│       └─► Robotic arm guidance simulation                       │
│                                                                 │
│  06_Unity_Haptic_Touch ──► Force feedback on screw contact     │
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
├── 01_Slicer_FiducialScrews/       ← Simulated bone-anchored screws in MRI
│   ├── README.md
│   └── scripts/
│
├── 02_Slicer_MRI_to_CT/            ← MRI → Synthetic CT conversion
│   ├── README.md
│   └── scripts/
│
├── 03_Slicer_Segmentation/         ← Skull, brain, tumour segmentation
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

### [01 — Fiducial Screw Simulation](01_Slicer_FiducialScrews/README.md)
**Starting point of the pipeline.** Simulates bone-anchored fiducial screws by burning bright cylindrical signals directly into the MRI voxel array, replicating the appearance of CuSO₄-filled plastic screws implanted before scanning. Produces a realistic pre-operative MRI dataset where students must identify and localise 9 screws distributed in a 3×3 grid on the parietal skull surface.

**Key output:** `MRI_WithScrews.nrrd` (student dataset) + `ScrewFiducials_GroundTruth.fcsv` (teacher answer key)

**Key tools:** 3D Slicer Python Interactor, NumPy, VTK

---

### [02 — MRI to Synthetic CT Conversion](02_Slicer_MRI_to_CT/README.md)
Converts the MRI (now containing screw signals) to synthetic CT using the **FedSynthCT-Brain** Fu Model — the best-performing of the three available architectures. Synthetic CT provides Hounsfield Unit values needed for bone segmentation and dose planning.

**Key input:** `MRI_WithScrews.nrrd`
**Key output:** `MRBrainTumor1_CT_FuModel`

**Key tools:** 3D Slicer, SlicerModalityConverter (Image Synthesis → ModalityConverter)

---

### [03 — Segmentation and 3D Reconstruction](03_Slicer_Segmentation/README.md)
Segments anatomical structures from the synthetic CT and MRI:
- **Skull** — threshold-based segmentation with manual cleanup of inferior structures
- **Brain** — HDBrain extension (deep learning)
- **Tumour** — semi-automatic segmentation with statistics

Exports 3D surface meshes (OBJ/STL) for Unity import.

**Key tools:** 3D Slicer Segment Editor, HDBrain, SurfaceWrapSolidify

---

### [04 — OpenIGTLink Communication](04_OpenIGT_Communication/README.md)
Establishes real-time bidirectional communication between 3D Slicer and Unity using the **OpenIGTLink** protocol. Enables live streaming of transform matrices, point clouds, volume slices, and state messages.

**Key tools:** SlicerOpenIGTLink extension, OpenIGTLink Unity plugin

---

### [05 — Unity Core Simulator](05_Unity_Core_Simulator/README.md)
The main surgical simulation:
- Import and display skull mesh, brain volume, tumour model
- Interactive probe placement on fiducial screws
- **SVD-based rigid registration** (virtual → physical coordinate systems)
- Insertion trajectory planning and visualisation
- Robotic arm (Franka Emika) simulation

**Key tools:** Unity 2022.3+, C#, Math.NET Numerics (SVD)

---

### [06 — Haptic Touch Device](06_Unity_Haptic_Touch/README.md)
Integrates a **Touch haptic device** (3D Systems) with the Unity simulator to provide force feedback when the virtual probe contacts the skull surface or fiducial screws.

**Key tools:** Unity, OpenHaptics SDK, Touch device driver

---

### [07 — Augmented Reality](07_Unity_AR/README.md)
Projects the surgical plan (tumour location, insertion trajectory, fiducial grid) as an AR overlay onto a physical skull phantom.

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
git clone https://github.com/alberthp/RoboticStereotacticBrainBiopsy.git
cd RoboticStereotacticBrainBiopsy
```

Follow modules **in order**:

1. **[SETUP.md](SETUP.md)** — install all required software
2. **[01 — Fiducial Screws](01_Slicer_FiducialScrews/README.md)** — generate MRI with simulated screws
3. **[02 — MRI to CT](02_Slicer_MRI_to_CT/README.md)** — convert MRI to synthetic CT
4. **[03 — Segmentation](03_Slicer_Segmentation/README.md)** — segment skull, brain, tumour
5. **[04 — OpenIGT](04_OpenIGT_Communication/README.md)** — set up Slicer–Unity bridge
6. **[05 — Unity Simulator](05_Unity_Core_Simulator/README.md)** — run the surgical simulation
7. **[06 — Haptics](06_Unity_Haptic_Touch/README.md)** *(optional)* — haptic feedback
8. **[07 — AR](07_Unity_AR/README.md)** *(optional)* — augmented reality overlay

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

- Explain the role of bone-anchored fiducial markers in stereotactic surgery
- Understand why CT is preferred over MRI for rigid tissue imaging and how synthetic CT addresses this
- Perform threshold-based and deep-learning skull/brain segmentation in 3D Slicer
- Implement SVD-based point-to-point rigid registration in Unity/C#
- Measure and interpret Fiducial Localisation Error (FLE) and Target Registration Error (TRE)
- Describe the OpenIGTLink protocol and its role in surgical navigation systems
- Integrate haptic feedback and AR visualisation into a surgical simulation

---

## Contributing

Contributions are welcome. Please open an issue first to discuss proposed changes.

---

## Citation

If you use this repository in academic work:

> A. Hernansanz, *Robotic Stereotactic Brain Biopsy — An Open-Source Educational Simulation Pipeline*, GitHub, 2025.
> https://github.com/alberthp/RoboticStereotacticBrainBiopsy

For the MRI-to-CT conversion component:

> C.B. Raggio et al., *FedSynthCT-Brain*, Computers in Biology and Medicine, Vol. 192, 2025.
> https://doi.org/10.1016/j.compbiomed.2025.110160

---
## Author

**Albert Hernansanz Prats**

*albert.hernansanz@upf.edu · alberthp@gmail.com*

SYMBIOsis | Barcelona Centre for New Medical Technologies (BCN MedTech)
Department of Information and Communication Technologies
Universitat Pompeu Fabra (UPF)

---
## License

MIT License — see [LICENSE](LICENSE) for details.

The FedSynthCT models are licensed for **research purposes only**.
See [SlicerModalityConverter MODEL_LICENSE](https://github.com/ciroraggio/SlicerModalityConverter/blob/main/MODEL_LICENSE).

---

## Acknowledgements

- [SlicerModalityConverter](https://github.com/ciroraggio/SlicerModalityConverter) — C.B. Raggio, P. Zaffino, M.F. Spadea
- [3D Slicer](https://www.slicer.org/) — Fedorov et al., Magn Reson Imaging, 2012
- [OpenIGTLink](http://openigtlink.org/) — Tokuda et al., Int J Med Robot, 2009
