"""
export_data.py
==============
Exports all assets from the Slicer scene for Unity import.

Usage:
    Run in 3D Slicer Python Interactor (View → Python Interactor)
    Edit EXPORT_PATH before running.
"""

import os

# ── Configuration ────────────────────────────────────────────────────────────
EXPORT_PATH = r"C:\YourOutputFolder"   # <-- Change this

# ── Export ───────────────────────────────────────────────────────────────────
os.makedirs(EXPORT_PATH, exist_ok=True)

# 1 — MRI with screws (give to students)
mriNode = slicer.util.getNode("MRBrainTumor1")
slicer.util.exportNode(mriNode,
    os.path.join(EXPORT_PATH, "MRI_WithScrews.nrrd"))
print("1/4 saved: MRI_WithScrews.nrrd")

# 2 — Skull mesh
skullModel = slicer.util.getNode("SkullModel")
slicer.util.exportNode(skullModel,
    os.path.join(EXPORT_PATH, "SkullMesh.obj"))
print("2/4 saved: SkullMesh.obj")

# 3 — Ground truth fiducial centroids (teacher answer key)
markupsNode = slicer.util.getNode("FiducialMarks_List")
slicer.util.exportNode(markupsNode,
    os.path.join(EXPORT_PATH, "ScrewFiducials_GroundTruth.fcsv"))
print("3/4 saved: ScrewFiducials_GroundTruth.fcsv")

# 4 — Full Slicer scene backup
slicer.util.saveScene(
    os.path.join(EXPORT_PATH, "SlicerScene_WithScrews.mrb"))
print("4/4 saved: SlicerScene_WithScrews.mrb")

print(f"\nAll files saved to:\n{EXPORT_PATH}")
