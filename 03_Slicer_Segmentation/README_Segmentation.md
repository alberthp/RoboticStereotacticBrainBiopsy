# Screw Fiducial Marker Generator

Automated detection and placement of fiducial markers on segmented bone screws in **3D Slicer**, designed for surgical robotics registration pipelines.

---

## Context

In robotic stereotactic brain biopsy, **registration** is the process of aligning the pre-operative virtual plan (CT/MRI) with the patient's physical position on the operating table. Bone screws implanted prior to imaging serve as **fiducial markers** — geometrically stable landmarks identifiable both in the scan and physically during surgery.

This script automates the placement of a **control point at the tip of each screw** (the exposed head, protruding from the skull surface), which is the point the surgeon will physically touch with the registration probe intra-operatively.

---

## Pipeline

![Pipeline diagram](images/pipeline_diagram.svg)

The pipeline has two manual steps (user action required) and two automated steps (computed by the script).

**Step 1 — Segment editor (manual):** The user segments all screws together into a single segment using 3D Slicer's Segment Editor. Threshold-based or paint tools work well for metal implants on CT.

**Step 2 — Identify volumes (automated):** `scipy.ndimage.label()` splits the single segment into one connected component per screw. The GUI shows a size bar chart and flags small fragments as likely segmentation artifacts — these should be removed in Segment Editor before proceeding.

**Step 3 — Compute fiducials (automated):** For each screw component, the script extracts all voxel RAS coordinates, computes the centroid (mean position), runs PCA to find the long axis, and projects all voxels onto that axis to find both endpoints. The endpoint farthest from the global centroid of all screws is selected as the tip (exposed screw head).

**Step 4 — Fine-tune tips (manual):** The GUI allows moving each tip point ± mm along R, A and S axes with precise step control. Points can also be dragged interactively in any 3D or 2D Slicer view.

---

## Key Algorithm: PCA-based Tip Detection

Each screw is treated as a **point cloud** of voxel coordinates. Principal Component Analysis finds the direction of maximum variance, which corresponds to the screw's long axis regardless of its orientation in space. This makes the method robust to:

- Screws at any angle (not just vertical or axis-aligned)
- Screws with different orientations relative to each other
- Any imaging modality (CT recommended for metal implants)

The **tip vs base disambiguation** uses the global centroid of all screws as a reference: the tip (screw head) always points away from the bone mass, while the base is anchored inside it.

---

## Artifact Detection

Small disconnected voxel clusters appear in segmentations due to noise, partial volume effects, or image artefacts near metal. The script automatically flags components whose size falls below a user-adjustable percentage of the median screw size:

```
threshold = (slider_value / 100) × median_voxel_count

default: 20% of median
```

The bar chart makes the gap between real screws and artifacts immediately visible. Artifacts should be removed in Segment Editor before computing fiducials.

---

## Results

The following screenshots show the script output on a real CT scan with 9 implanted bone screws.

### Close-up view — fiducial markers and axis lines

![Close-up 3D view showing ScrewTips in orange, ScrewCentroids in cyan and axis lines per screw](images/result_closeup.png)

Each screw produces three output elements:

- **Orange point** (`ScrewTip_XX`): the computed tip (exposed head), used as the fiducial marker for intra-operative registration. This is the point the surgeon touches with the registration probe.
- **Cyan point** (`Ctr_Screw_XX`): the geometric centroid of the screw volume, used as a locked reference.
- **Yellow-green line** (`Axis_Screw_XX`): the PCA long axis from centroid to tip, visualising the detected screw orientation. The length annotation (e.g. `6.730 mm`) is the centroid-to-tip distance — approximately half the visible screw length.

### Overview — all 9 screws on the skull

![Overview 3D view showing all 9 detected screws distributed over the superior parietal skull surface](images/result_overview.png)

All 9 screws are correctly detected and labelled, distributed across the superior parietal region of the skull in the expected anatomical configuration for the stereotactic brain biopsy registration procedure.

---

## Requirements

- 3D Slicer 5.x
- Python packages (included in Slicer's Python): `numpy`, `scipy`, `vtk`, `qt`
- A segmentation node containing all screws in a single segment

---

## Usage

1. Open 3D Slicer and load your CT/MRI volume
2. Segment all screws into a single segment using **Segment Editor**
3. Open the **Python Console** (`Ctrl+3`)
4. Load and run the script:
   ```python
   exec(open(r"path/to/screw_fiducial_generator.py").read())
   ```
5. Follow the 4-step GUI

---

## Output Nodes

| Node | Color | Type | Description |
|---|---|---|---|
| `ScrewTips` | Orange | MarkupsFiducialNode | One point per screw tip — interactive, drag to fine-tune |
| `ScrewCentroids` | Cyan | MarkupsFiducialNode | One point per screw centroid — locked reference |
| `ScrewAxes/` | Yellow | Folder | Subject Hierarchy folder with one axis line per screw |
| `PREVIEW_ValidScrews` | Green cross | MarkupsFiducialNode | Temporary preview during Step 2 — removed after Step 3 |
| `PREVIEW_Artifacts` | Red starburst | MarkupsFiducialNode | Temporary artifact preview — removed after Step 3 |

---

## Repository Structure

```
01_Slicer_FiducialScrews/
├── screw_fiducial_generator.py   ← main script (run in Slicer Python Console)
├── README.md
└── images/
    ├── pipeline_diagram.svg      ← pipeline diagram
    ├── result_closeup.png        ← close-up result screenshot
    └── result_overview.png       ← overview result screenshot
```

---

## Limitations

- Screws must be **fully separated** in the segmentation (no touching or overlapping volumes)
- Heavily fragmented segmentations will confuse the connected component step — clean the segmentation first using Islands or Erase in Segment Editor
- The tip/base disambiguation assumes screw heads point **away** from the centroid of the screw cluster. If your configuration is unusual, adjust `find_tip_and_base()` in the script
