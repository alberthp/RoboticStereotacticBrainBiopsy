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

Expected output: CT range approximately `-1024` to `1600` HU. Bone should appear bright white in the axial view.

---

## Output

| Node | Type | Description |
|---|---|---|
| `MRBrainTumor1_CT_FuModel` | Scalar Volume | Synthetic CT [256×256×256] in Hounsfield Units |

This volume is used as input for **[02 — Segmentation](../02_Slicer_Segmentation/README.md)**.

---

## Important Note on Volume Coverage

The output CT has dimensions 256×256×256 regardless of the input MRI dimensions. For MRBrainTumor1 (112 slices), the CT covers a larger S range (up to +280mm) than the original MRI (up to +79mm). This is important when working with coordinates across both volumes — see module 03 for details.

---

## Citation

> C.B. Raggio et al., *FedSynthCT-Brain: A federated learning framework for multi-institutional brain MRI-to-CT synthesis*, Computers in Biology and Medicine, Volume 192, Part A, 2025, 110160.
> https://doi.org/10.1016/j.compbiomed.2025.110160

> Raggio C.B., Zaffino P., Spadea M.F., *SlicerModalityConverter: An Open-Source 3D Slicer Extension for Medical Image-to-Image Translation*, 2025.
> https://github.com/ciroraggio/SlicerModalityConverter
