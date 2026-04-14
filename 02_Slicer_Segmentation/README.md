# 02 — Segmentation and 3D Reconstruction

Segments skull, brain, and tumour from the synthetic CT and MRI.

## Steps

### Skull Segmentation
1. Open Modules → Segment Editor
2. Select MRBrainTumor1_CT_FuModel as master volume
3. Add segment → name "Skull"
4. Threshold: 200–700 HU → Apply
5. Islands → Keep largest island
6. Scissors: remove inferior structures (temporal bone, skull base)
7. Smoothing → Closing (2mm kernel)

### Brain Segmentation
1. Install HDBrain extension
2. Modules → HDBrain → Run on MRBrainTumor1

### Tumour Segmentation
1. Segment Editor → Add segment "Tumour"
2. Use Paint / Draw tools to delineate tumour in all planes
3. Modules → Segment Statistics → compute centroid

### Export to Models
Run in Python Interactor for each segment:
```python
# See scripts/export_segments.py
```

## Output
- `SkullMesh.obj` — skull surface mesh
- `BrainMesh.obj` — brain surface mesh  
- `TumourMesh.obj` — tumour surface mesh
- `TumourCentroid.fcsv` — tumour centroid coordinates
