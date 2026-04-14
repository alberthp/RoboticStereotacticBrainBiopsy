# 01 — MRI to Synthetic CT Conversion

Converts T1-weighted MRI brain scans to synthetic CT (sCT) using the **FedSynthCT-Brain** federated learning model, integrated in the **SlicerModalityConverter** extension. The synthetic CT provides Hounsfield Unit (HU) values needed for bone segmentation and radiotherapy dose planning — tasks where MRI alone is insufficient.

---

## Why Synthetic CT?

MRI provides excellent soft tissue contrast but cannot reliably distinguish bone from other structures because cortical bone appears dark and featureless. CT is the gold standard for rigid tissue imaging, but requires additional ionising radiation exposure. Synthetic CT eliminates the need for a separate CT scan by learning the MRI → CT mapping from paired training data using deep learning.

---

## Step 1 — Install the ModalityConverter Extension

1. Open **3D Slicer** (≥ 5.8)
2. Go to **Edit → Extension Manager** (or click the extension icon in the toolbar)
3. In the search box type: `ModalityConverter`
4. Click **Install** next to **SlicerModalityConverter**
5. When installation completes, click **Restart Slicer**

> The extension is listed under the **Image Synthesis** category in the Extension Manager.

---

## Step 2 — Load Sample Data

1. Go to **File → Download Sample Data**
2. Click **MRBrainTumor1** — the volume loads automatically
3. Verify it appears in the slice views as a T1-weighted MRI brain scan

---

## Step 3 — Open the ModalityConverter Module

Go to **Modules → Image Synthesis → ModalityConverter**

Or use the module search bar (Ctrl+F) and type `ModalityConverter`

---

## Step 4 — Configure the Module

Set the following parameters (see screenshot below):

| Parameter | Value | Notes |
|---|---|---|
| **Input volume** | `MRBrainTumor1` | The T1w MRI loaded in Step 2 |
| **ROI Mask** | `None` | Leave empty — do not use a mask |
| **Model** | `[T1w MRI-to-CT] [Brain] FedSynthCT MRI-T1w Fu Model` | See model selection below |
| **Output volume** | `MRBrainTumor1_CT_FuModel` | Name the output clearly |
| **Device** | `gpu 0 - NVIDIA GeForce ...` | Use GPU if available — significantly faster |

![ModalityConverter configuration](modalityconverter_config.png)

---

## Model Selection — Why the Fu Model?

Three brain MRI-to-CT models are available, all trained using the FedSynthCT-Brain federated learning framework:

| Model | Architecture | Recommendation |
|---|---|---|
| `FedSynthCT MRI-T1w Li Model` | U-Net (Li et al.) | Fastest — lightest architecture |
| **`FedSynthCT MRI-T1w Fu Model`** | **U-Net (Fu et al.)** | **Best results — use this one** |
| `FedSynthCT MRI-T1w Spadea Model` | U-Net (Spadea, Pileggi et al.) | Alternative architecture |

**Use the Fu Model** — among the three it produces the most accurate synthetic CT with the best bone contrast and fewest artefacts on the MRBrainTumor1 dataset. This is critical for the downstream skull segmentation step.

> All three models were trained using the same federated learning framework across 4 European and American centres. The difference is in the U-Net backbone architecture used for image-to-image translation.

---

## Step 5 — Run the Conversion

1. Click **Run**
2. The status bar shows `Processing completed.` when done (30–120 seconds depending on GPU/CPU)
3. The output volume `MRBrainTumor1_CT_FuModel` appears in the Data module

---

## Step 6 — Verify the Output

Switch to the CT volume and set a bone window to confirm the skull is clearly visible:

```python
# Run in Python Interactor (View → Python Interactor)
ctNode = slicer.util.getNode("MRBrainTumor1_CT_FuModel")
slicer.util.setSliceViewerLayers(background=ctNode, fit=True)
displayNode = ctNode.GetVolumeDisplayNode()
displayNode.SetWindow(1500)
displayNode.SetLevel(400)
print(f"CT range: {ctNode.GetImageData().GetScalarRange()}")
```

## Step 6 — Verify the Output

Switch to the CT volume and set a bone window to confirm the skull is clearly visible:

```python
# Run in Python Interactor (View → Python Interactor)
ctNode = slicer.util.getNode("MRBrainTumor1_CT_FuModel")
slicer.util.setSliceViewerLayers(background=ctNode, fit=True)
displayNode = ctNode.GetVolumeDisplayNode()
displayNode.SetWindow(1500)
displayNode.SetLevel(400)
print(f"CT range: {ctNode.GetImageData().GetScalarRange()}")
```

Expected output: CT range approximately `-1024` to `1600` HU. Bone should appear bright white in the axial view.

### Expected result

![Synthetic CT with screws — Fu Model](screenshots/01_CT_WithScrews_FuModel.png)

The synthetic CT clearly shows:
- **Axial (top-left)** — bright white skull ring with the 9 screw signals visible as high-intensity spots
- **3D rendering (top-right)** — fiducial marker labels (F_1-1 through F_3-3) overlaid on the skull surface
- **Coronal (bottom-left)** and **Sagittal (bottom-right)** — clean bone contrast with soft tissue visible

The screws burned into the MRI in module 01 are preserved and visible in the synthetic CT — confirming the full pipeline is working correctly.

### Bone window — high contrast view

For clearer bone visualisation, narrow the window to emphasise the cortical ring:

```python
displayNode.SetWindow(400)
displayNode.SetLevel(200)
```

![Synthetic CT — bone window](screenshots/02_CT_BoneWindow.png)

With this window setting the skull cortex appears pure white and the soft tissue disappears, making it ideal for segmentation (module 03). The 3D rendering (top-right) shows the skull surface geometry clearly.

---

## Output

| Node | Type | Description |
|---|---|---|
| `MRBrainTumor1_CT_FuModel` | Scalar Volume | Synthetic CT [256×256×256] in Hounsfield Units |

This volume is used as input for **[02 — Segmentation](../03_Slicer_Segmentation/README.md)**.

---

## Known Issue — Vertical Misalignment in 3D Rendering

When both `MRBrainTumor1` (original MRI) and `BrainTumor1_Screws_CTFu` (synthetic CT) are displayed simultaneously in the 3D view, a **vertical offset of ~100mm** is visible between the two volumes. The CT skull appears shifted upward relative to the MRI head rendering.

**This is expected behaviour — not a bug.**

| Property | MRI | Synthetic CT |
|---|---|---|
| S range | -77.7 to **+79.1 mm** | -77.7 to **+280.7 mm** |
| Slices | 112 | 256 |
| Volume center (S) | 0.7 mm | **101.5 mm** |
| S coverage | 156.8 mm | **358.4 mm** |

**Root cause:** The ModalityConverter preprocessing pads the input MRI to a fixed 256×256×256 volume before inference. The output CT therefore has **144 extra slices (201.6 mm) above the top of the original MRI**, shifting the 3D bounding box center upward by ~101mm.

**Why 2D views are not affected:** Both volumes share the same origin (S = -77.7 mm) and spacing (1.4 mm/slice). In 2D slice views, the same S coordinate maps to the same anatomy in both volumes — the misalignment is invisible because you are comparing individual slices, not bounding boxes.

**Impact on the pipeline:** None. Segmentation, fiducial placement, and registration all use slice coordinates (RAS positions) which are correctly aligned. The 3D rendering discrepancy is purely cosmetic.

**To avoid confusion in the 3D view:** Display only one volume at a time, or use the Volume Rendering module to crop the CT rendering to the MRI's S range:

```python
# Crop CT rendering to match MRI S coverage
ctNode = slicer.util.getNode("BrainTumor1_Screws_CTFu")
vrLogic = slicer.modules.volumerendering.logic()
vrNode  = vrLogic.GetFirstVolumeRenderingDisplayNode(ctNode)
if vrNode:
    roiNode = vrNode.GetROINode()
    roiNode.SetXYZ(0, 0, 0.7)          # MRI center
    roiNode.SetRadiusXYZ(120, 120, 78) # MRI half-extents
    vrNode.SetCroppingEnabled(True)
```

The output CT has dimensions 256×256×256 regardless of the input MRI dimensions. For MRBrainTumor1 (112 slices), the CT covers a larger S range (up to +280mm) than the original MRI (up to +79mm). This is important when working with coordinates across both volumes — see module 03 for details.

---

## Citation

> C.B. Raggio et al., *FedSynthCT-Brain: A federated learning framework for multi-institutional brain MRI-to-CT synthesis*, Computers in Biology and Medicine, Volume 192, Part A, 2025, 110160.
> https://doi.org/10.1016/j.compbiomed.2025.110160

> Raggio C.B., Zaffino P., Spadea M.F., *SlicerModalityConverter: An Open-Source 3D Slicer Extension for Medical Image-to-Image Translation*, 2025.
> https://github.com/ciroraggio/SlicerModalityConverter
