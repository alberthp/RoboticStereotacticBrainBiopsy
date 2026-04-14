# Simulated Bone-Anchored Fiducial Screws in MRI
### 3D Slicer Python Tutorial — Surgical Registration Simulation

This guide explains how to simulate bone-anchored fiducial screw markers in a T1-weighted MRI volume using 3D Slicer. The result is a realistic pre-operative MRI dataset that students can use to practice fiducial identification, point placement, and surgical registration workflows.

---

## Overview

In stereotactic neurosurgery, bone-anchored fiducial screws are implanted in the skull before imaging. The screws are filled with MRI-visible material (e.g. copper-sulfate solution) and appear as bright cylindrical signals in T1w MRI. This tutorial simulates that process digitally by burning synthetic screw signals directly into the MRI voxel array.

### Pedagogical Workflow

```
Teacher: Generate MRI_WithScrews.nrrd  (this guide)
              ↓
Student: Load MRI → identify 9 screws visually → place Markup points
              ↓
Student: Run ModalityConverter MRI → synthetic CT
              ↓
Student: Segment skull → export 3D mesh
              ↓
Student: Export fiducial list → Unity registration simulation
              ↓
Teacher: Compare student points vs ground truth → measure FLE
```

---

## Fiducial Reference Point Coordinates

The 9 screw positions are defined as a **3×3 grid on the parietal skull surface** of MRBrainTumor1, within the MRI coverage (S = 50–68 mm).

### Grid layout

```
         R- (Left)       R=0        R+ (Right)
              |             |             |
A+ (Post) -- F_3-1 ------ F_3-2 ------ F_3-3   S ≈ 65–68mm
              |             |             |
              F_2-1 ------ F_2-2 ------ F_2-3   S ≈ 59–63mm
              |             |             |
A- (Ant)  -- F_1-1 ------ F_1-2 ------ F_1-3   S ≈ 50–55mm
```

### Coordinates (RAS, mm)

| Label | R (mm) | A (mm) | S (mm) | Position |
|---|---|---|---|---|
| F_1-1 | -17.344 | 58.255 | 50.503 | Left-Anterior |
| F_1-2 |   3.281 | 58.255 | 54.755 | Center-Anterior |
| F_1-3 |  22.969 | 58.255 | 50.830 | Right-Anterior |
| F_2-1 | -17.344 | 43.736 | 59.998 | Left-Middle |
| F_2-2 |   3.281 | 43.736 | 62.720 | Center (grid center) |
| F_2-3 |  22.969 | 43.736 | 59.370 | Right-Middle |
| F_3-1 | -17.344 | 29.794 | 64.897 | Left-Posterior |
| F_3-2 |   3.281 | 29.794 | 68.495 | Center-Posterior |
| F_3-3 |  22.969 | 29.794 | 65.232 | Right-Posterior |

> Spacing: ~20mm along R axis, ~14mm along A axis.
> The S coordinate varies naturally with skull curvature.

### Files

The full coordinates with copy-paste Python loader are in:
**[fiducial_reference_points.txt](fiducial_reference_points.txt)**

### Load into Slicer automatically (copy-paste into Python Interactor)

```python
import numpy as np

POINTS = [
    ("F_1-1", [-17.344, 58.255, 50.503]),
    ("F_1-2", [  3.281, 58.255, 54.755]),
    ("F_1-3", [ 22.969, 58.255, 50.830]),
    ("F_2-1", [-17.344, 43.736, 59.998]),
    ("F_2-2", [  3.281, 43.736, 62.720]),
    ("F_2-3", [ 22.969, 43.736, 59.370]),
    ("F_3-1", [-17.344, 29.794, 64.897]),
    ("F_3-2", [  3.281, 29.794, 68.495]),
    ("F_3-3", [ 22.969, 29.794, 65.232]),
]

node = slicer.mrmlScene.AddNewNodeByClass(
    "vtkMRMLMarkupsFiducialNode", "FiducialMarks_List")
for label, pos in POINTS:
    idx = node.AddControlPoint(pos)
    node.SetNthControlPointLabel(idx, label)
print(f"Loaded {node.GetNumberOfControlPoints()} points.")
```

---

## Requirements

- **3D Slicer** ≥ 5.8 ([download](https://download.slicer.org/))
- **SlicerModalityConverter** extension (install via Extension Manager)
- Python packages: `numpy`, `vtk` (both bundled with Slicer)
- Sample data: `MRBrainTumor1` (available via Slicer Sample Data module)

---

## Step 1 — Load Sample Data

1. Open 3D Slicer
2. Go to **File → Download Sample Data**
3. Click **MRBrainTumor1** to download and load the T1-weighted MRI
4. Verify the volume appears in the slice views

> **Note:** MRBrainTumor1 is a T1w MRI with dimensions 256×256×112 and spacing 0.938×0.938×1.4 mm. It covers S = -77.7 to +79.1 mm in RAS space.

---

## Step 2 — Generate Synthetic CT (ModalityConverter)

1. Go to **Modules → ModalityConverter**
2. Set **Input volume**: `MRBrainTumor1`
3. Set **Model**: `[T1w MRI-to-CT] [Brain] FedSynthCT MRI-T1w Fu Model`
4. Set **Output volume**: create new → name `MRBrainTumor1_CT_FuModel`
5. Click **Run** and wait for processing to complete

> The synthetic CT is needed for skull segmentation. It provides HU values that allow threshold-based bone segmentation.

---

## Step 3 — Segment the Skull

1. Go to **Modules → Segment Editor**
2. Click **Add** to create a new segment — name it `Skull`
3. Select the **Threshold** effect
   - Set range approximately **200–700 HU**
   - Click **Apply**
4. Use **Islands → Keep largest island** to remove scattered noise
5. Use **Scissors** tool to remove inferior skull structures (temporal bone, skull base) — keep only frontal and parietal regions
6. Use **Smoothing → Closing** (kernel 2–3 mm) to fill small gaps

### Export Skull as Model Node

Run in the **Python Interactor** (`View → Python Interactor`):

```python
segNode   = slicer.util.getNode("Segmentation")   # your segmentation name
skullModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "SkullModel")
seg        = segNode.GetSegmentation()
segmentId  = seg.GetNthSegmentID(0)

slicer.modules.segmentations.logic().ExportSegmentToRepresentationNode(
    seg.GetSegment(segmentId), skullModel
)

# Rename if Slicer used segment name instead
skullModel.SetName("SkullModel")
print("Skull model points:", skullModel.GetPolyData().GetNumberOfPoints())
```

Expected output: `Skull model points: ~150000+`

---

## Step 4 — Define the 9 Fiducial Point Positions

Place a 3×3 grid of Markup points on the skull surface in the **frontal/parietal region** within the MRI coverage (S = 50–76 mm for MRBrainTumor1).

### Manual placement (recommended for students)

1. In the **Markups toolbar**, click the dropdown → **Point List**
2. Name the new node exactly: `FiducialMarks_List`
3. In the 3D view, click directly on the skull surface to place each point
4. Name points `F_1-1` through `F_3-3` following the 3×3 grid convention:

```
F_1-1  F_1-2  F_1-3      ← Row 1 (most anterior / inferior)
F_2-1  F_2-2  F_2-3      ← Row 2 (middle)
F_3-1  F_3-2  F_3-3      ← Row 3 (most posterior / superior)
```

Space points approximately **12–15 mm** apart.

> **Tip:** Use the axial slice view at S = 55–75 mm to verify each point sits on the outer skull surface (bright ring in the MRI).

### Verify all 9 points

```python
markupsNode = slicer.util.getNode("FiducialMarks_List")
print(f"Points placed: {markupsNode.GetNumberOfControlPoints()}")
for i in range(markupsNode.GetNumberOfControlPoints()):
    pos = [0.0, 0.0, 0.0]
    markupsNode.GetNthControlPointPositionWorld(i, pos)
    label = markupsNode.GetNthControlPointLabel(i)
    print(f"  {label}: R={pos[0]:.3f}, A={pos[1]:.3f}, S={pos[2]:.3f}")
```

### Reference coordinates (MRBrainTumor1)

The following coordinates were used in the original tutorial session and can be loaded directly if manual placement is not required:

```python
import numpy as np

# Pre-defined 3x3 grid on parietal region — S range: 50–68 mm
REFERENCE_POINTS = [
    ("F_1-1", [-17.344, 58.255, 50.503]),
    ("F_1-2", [  3.281, 58.255, 54.755]),
    ("F_1-3", [ 22.969, 58.255, 50.830]),
    ("F_2-1", [-17.344, 43.736, 59.998]),
    ("F_2-2", [  3.281, 43.736, 62.720]),
    ("F_2-3", [ 22.969, 43.736, 59.370]),
    ("F_3-1", [-17.344, 29.794, 64.897]),
    ("F_3-2", [  3.281, 29.794, 68.495]),
    ("F_3-3", [ 22.969, 29.794, 65.232]),
]

# Load into Slicer as a new Markup node
markupsNode = slicer.mrmlScene.AddNewNodeByClass(
    "vtkMRMLMarkupsFiducialNode", "FiducialMarks_List")

for label, pos in REFERENCE_POINTS:
    idx = markupsNode.AddControlPoint(pos)
    markupsNode.SetNthControlPointLabel(idx, label)

print(f"Loaded {markupsNode.GetNumberOfControlPoints()} reference points.")
```

---

## Step 5 — Burn Screw Signals into the MRI Volume

This script writes bright cylindrical voxel patterns into `MRBrainTumor1`, simulating the MRI signal of CuSO₄-filled plastic screws. Each screw protrudes 3 mm above the skull surface and extends 9 mm into the bone.

### Screw parameters

| Parameter | Value | Notes |
|---|---|---|
| Radius | 0.75 mm | 1.5 mm diameter — realistic small screw |
| Length | 12 mm | 3 mm protrusion + 9 mm into bone |
| Protrusion | 3 mm | Above skull surface — touchable by probe |
| Intensity | 900 | Well above brightest tissue (695 max in MRBrainTumor1) |

### Full burn script

```python
import numpy as np
import vtk

# ── Step 5a: Read live point positions from Markups node ────────────────
markupsNode = slicer.util.getNode("FiducialMarks_List")

# Brain center used for inward normal computation
# (midpoint of MRI volume: R=0, A=0, S=1)
brainCenter = np.array([0.0, 0.0, 1.0])

screwData_MRI = []
for i in range(markupsNode.GetNumberOfControlPoints()):
    pos = [0.0, 0.0, 0.0]
    markupsNode.GetNthControlPointPositionWorld(i, pos)
    label = markupsNode.GetNthControlPointLabel(i)
    pos = np.array(pos)
    # Inward normal = direction from surface point toward brain center
    inward = brainCenter - pos
    inward = inward / np.linalg.norm(inward)
    screwData_MRI.append((label, pos, inward))

print(f"Loaded {len(screwData_MRI)} screw positions.")

# ── Step 5b: Get volume and transform ───────────────────────────────────
mriNode  = slicer.util.getNode("MRBrainTumor1")
mriArray = slicer.util.arrayFromVolume(mriNode)   # shape: (K, J, I)
print(f"Volume shape: {mriArray.shape}  Max before: {mriArray.max():.1f}")

rasToIJK = vtk.vtkMatrix4x4()
mriNode.GetRASToIJKMatrix(rasToIJK)

# ── Step 5c: Screw parameters ───────────────────────────────────────────
SCREW_INTENSITY  = 900     # HU-equivalent signal intensity
SCREW_RADIUS_MM  = 0.75    # mm — radius of screw cylinder
SCREW_LENGTH_MM  = 12.0    # mm — total shaft length
PROTRUSION_MM    = 3.0     # mm — amount protruding above skull surface
N_DEPTH          = 120     # sampling density along shaft
N_RING           = 16      # sampling density around circumference
N_RADIAL         = 6       # sampling density across disc radius

# ── Step 5d: Burn each screw ────────────────────────────────────────────
screwCentroids = []
totalWritten   = 0

for label, pos, inward in screwData_MRI:

    # Start OUTSIDE skull surface (protrusion)
    startPos = pos + (-inward) * PROTRUSION_MM
    centroid = startPos + inward * (SCREW_LENGTH_MM / 2.0)
    screwCentroids.append((label, centroid))

    # Local coordinate frame perpendicular to inward normal
    arb = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(inward, arb)) > 0.9:
        arb = np.array([0.0, 1.0, 0.0])
    perp1 = np.cross(inward, arb);  perp1 /= np.linalg.norm(perp1)
    perp2 = np.cross(inward, perp1)

    voxelsWritten = 0
    for depth in np.linspace(0, SCREW_LENGTH_MM, N_DEPTH):
        axisPoint = startPos + inward * depth
        for r in np.linspace(0, SCREW_RADIUS_MM, N_RADIAL):
            nTheta = max(1, int(N_RING * r / SCREW_RADIUS_MM))
            for theta in np.linspace(0, 2*np.pi, nTheta, endpoint=False):
                diskPoint = (axisPoint
                             + r * np.cos(theta) * perp1
                             + r * np.sin(theta) * perp2)
                ijk = rasToIJK.MultiplyPoint(
                    [diskPoint[0], diskPoint[1], diskPoint[2], 1.0])
                I = int(round(ijk[0]))
                J = int(round(ijk[1]))
                K = int(round(ijk[2]))
                if (0 <= K < mriArray.shape[0] and
                    0 <= J < mriArray.shape[1] and
                    0 <= I < mriArray.shape[2]):
                    mriArray[K, J, I] = SCREW_INTENSITY
                    voxelsWritten += 1

    totalWritten += voxelsWritten
    print(f"  {label}: {voxelsWritten} voxels written")

# ── Step 5e: Push back to volume and refresh display ────────────────────
slicer.util.updateVolumeFromArray(mriNode, mriArray)
mriNode.Modified()
print(f"\nTotal voxels written: {totalWritten}")
print(f"Max value after burn: {mriArray.max():.1f}")

displayNode = mriNode.GetVolumeDisplayNode()
displayNode.SetAutoWindowLevel(0)
displayNode.SetWindow(600)
displayNode.SetLevel(300)
slicer.util.setSliceViewerLayers(background=mriNode, fit=True)

# Jump to center screw F_2-2 (index 4)
center = screwCentroids[4][1]
slicer.modules.markups.logic().JumpSlicesToLocation(
    center[0], center[1], center[2], True)
print(f"\nJumped to F_2-2 centroid: {[round(c,1) for c in center]}")
print("Done — scroll axial slices to verify bright screw cross-sections.")
```

### Verify the burn

```python
import numpy as np

mriArray = slicer.util.arrayFromVolume(slicer.util.getNode("MRBrainTumor1"))
screwVoxels = np.sum(mriArray >= 899)
slices = np.where(np.any(mriArray >= 899, axis=(1,2)))[0]
print(f"Screw voxels: {screwVoxels}")
print(f"K slices with screws: {slices.min()} to {slices.max()}")
print(f"Max value: {mriArray.max():.1f}")
```

---

## Step 6 — Update Markup List to Screw Centroids

Update the Markup node so the stored coordinates match the **centroid of each screw shaft** (the point a probe tip would touch):

```python
markupsNode = slicer.util.getNode("FiducialMarks_List")

for i, (label, centroid) in enumerate(screwCentroids):
    markupsNode.SetNthControlPointPositionWorld(
        i, centroid[0], centroid[1], centroid[2])
    markupsNode.SetNthControlPointLabel(i, label)
    print(f"Updated {label}: {[round(c,2) for c in centroid]}")

print("Fiducial list updated to screw centroids.")
```

---

## Step 7 — Export Data

### Option A — Export via Python (recommended)

```python
import os

# Change this path to your output folder
EXPORT_PATH = r"C:\YourOutputFolder"
os.makedirs(EXPORT_PATH, exist_ok=True)

# 1 — MRI with screws burned in (give this to students)
mriNode = slicer.util.getNode("MRBrainTumor1")
slicer.util.exportNode(mriNode,
    os.path.join(EXPORT_PATH, "MRI_WithScrews.nrrd"))
print("1/4 saved: MRI_WithScrews.nrrd")

# 2 — Skull mesh for Unity
skullModel = slicer.util.getNode("SkullModel")
slicer.util.exportNode(skullModel,
    os.path.join(EXPORT_PATH, "SkullMesh.obj"))
print("2/4 saved: SkullMesh.obj")

# 3 — Ground truth fiducial centroids (keep for evaluation)
markupsNode = slicer.util.getNode("FiducialMarks_List")
slicer.util.exportNode(markupsNode,
    os.path.join(EXPORT_PATH, "ScrewFiducials_GroundTruth.fcsv"))
print("3/4 saved: ScrewFiducials_GroundTruth.fcsv")

# 4 — Full Slicer scene backup
slicer.util.saveScene(
    os.path.join(EXPORT_PATH, "SlicerScene_WithScrews.mrb"))
print("4/4 saved: SlicerScene_WithScrews.mrb")

print(f"\nAll files saved to: {EXPORT_PATH}")
```

### Option B — Export via Slicer GUI

1. **MRI volume**: `File → Export Data` → select `MRBrainTumor1` → format `NRRD`
2. **Skull mesh**: `File → Export Data` → select `SkullModel` → format `OBJ`
3. **Fiducials**: In Markups module → `Export/Import Table` → export as `.fcsv`
4. **Full scene**: `File → Save Data` → save as `.mrb` (Slicer bundle)

---

## Output Files Summary

| File | Format | Contents | Recipient |
|---|---|---|---|
| `MRI_WithScrews.nrrd` | NRRD | T1w MRI + 9 screw signals | **Students** |
| `SkullMesh.obj` | OBJ | 3D skull surface mesh | Unity import |
| `ScrewFiducials_GroundTruth.fcsv` | CSV | 9 screw centroid coordinates | **Teacher (answer key)** |
| `SlicerScene_WithScrews.mrb` | MRB | Complete Slicer scene backup | Teacher backup |

---

## Student Task (after receiving MRI_WithScrews.nrrd)

1. Load `MRI_WithScrews.nrrd` in 3D Slicer
2. Scroll through axial slices — identify the 9 bright screw cross-sections on the skull ring
3. Create a new **Point List** Markup node named `StudentFiducials`
4. Place one point at the **center of each screw** (centroid of the bright cylinder)
5. Export as `StudentFiducials.fcsv`
6. Run ModalityConverter (MRI → synthetic CT)
7. Segment the skull and export as `SkullMesh_Student.obj`
8. Submit both files for registration error evaluation

---

## Registration Error Evaluation

Compare student fiducials against ground truth to compute the **Fiducial Localization Error (FLE)**:

```python
import numpy as np

# Load ground truth (teacher)
gt = {
    "F_1-1": [-17.344, 58.255, 50.503],
    "F_1-2": [  3.281, 58.255, 54.755],
    "F_1-3": [ 22.969, 58.255, 50.830],
    "F_2-1": [-17.344, 43.736, 59.998],
    "F_2-2": [  3.281, 43.736, 62.720],
    "F_2-3": [ 22.969, 43.736, 59.370],
    "F_3-1": [-17.344, 29.794, 64.897],
    "F_3-2": [  3.281, 29.794, 68.495],
    "F_3-3": [ 22.969, 29.794, 65.232],
}

# Load student fiducials from FiducialMarks_List
studentNode = slicer.util.getNode("StudentFiducials")
errors = []
print("Fiducial Localization Error (FLE) per screw:")
for i in range(studentNode.GetNumberOfControlPoints()):
    pos = [0.0, 0.0, 0.0]
    studentNode.GetNthControlPointPositionWorld(i, pos)
    label = studentNode.GetNthControlPointLabel(i)
    if label in gt:
        error = np.linalg.norm(np.array(pos) - np.array(gt[label]))
        errors.append(error)
        print(f"  {label}: {error:.2f} mm")

print(f"\nMean FLE: {np.mean(errors):.2f} mm")
print(f"Max  FLE: {np.max(errors):.2f} mm")
print(f"RMS  FLE: {np.sqrt(np.mean(np.array(errors)**2)):.2f} mm")
```

---

## Technical Notes

### Why geometric inward normals instead of mesh normals?

The skull mesh was generated from the **synthetic CT** which has a different S-range (up to 280mm) than the original MRI (up to 79mm). After applying the -94mm S offset to bring points into MRI coverage, the mesh normals at those positions were unreliable. Instead, each inward normal is computed as the unit vector from the surface point toward the MRI volume center (0, 0, 1) — a robust geometric approximation for the parietal/frontal skull region.

### Coordinate systems

- Slicer uses **RAS** (Right-Anterior-Superior) coordinates in mm
- Unity uses **left-handed Y-up** coordinates
- When importing into Unity, apply: `unityPos = new Vector3(-slicerR, slicerS, slicerA)`

### MRI vs CT for screw visibility

| Modality | Screw signal | Bone signal | Contrast |
|---|---|---|---|
| T1w MRI | Bright (900) | Variable (~200–400) | Good |
| Synthetic CT | Would need ~3000 HU | ~400–700 HU | Excellent |

Screws are burned into the **MRI** because that is the clinically realistic scenario — patients are scanned with screws already implanted before surgery.

---

## Citation

If using the ModalityConverter (FedSynthCT) model in this workflow:

> C.B. Raggio et al., *FedSynthCT-Brain: A federated learning framework for multi-institutional brain MRI-to-CT synthesis*, Computers in Biology and Medicine, Volume 192, Part A, 2025, 110160. https://doi.org/10.1016/j.compbiomed.2025.110160

SlicerModalityConverter extension: https://github.com/ciroraggio/SlicerModalityConverter

---

## Screenshots needed

To complete this documentation with visual guidance, screenshots of the following steps would be helpful:

- [ ] Step 1: MRBrainTumor1 loaded in 4-panel view
- [ ] Step 2: ModalityConverter module UI with settings
- [ ] Step 3: Segment Editor with skull segmented
- [ ] Step 4: FiducialMarks_List with 9 points in 3D view
- [ ] Step 5: Final result — 4-panel view showing screws in all planes
- [ ] Step 5: 3D view showing screws protruding from skull surface
