# 01 — MRI to Synthetic CT Conversion

Converts T1-weighted MRI to synthetic CT using FedSynthCT-Brain via SlicerModalityConverter.

## Steps
1. Load MRBrainTumor1 (File → Download Sample Data)
2. Open Modules → ModalityConverter
3. Input: MRBrainTumor1 | Model: FedSynthCT Fu Model | Output: MRBrainTumor1_CT_FuModel
4. Click Run (GPU recommended)

## Output
- `MRBrainTumor1_CT_FuModel` — synthetic CT volume [256×256×256] in Hounsfield Units

## Citation
C.B. Raggio et al., FedSynthCT-Brain, Computers in Biology and Medicine, 2025.
https://doi.org/10.1016/j.compbiomed.2025.110160
