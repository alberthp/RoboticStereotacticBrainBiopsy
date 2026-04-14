"""
evaluate_fle.py
===============
Computes Fiducial Localisation Error (FLE) between student-placed
points and ground truth screw centroids.

Usage:
    Run in 3D Slicer Python Interactor after loading both:
    - FiducialMarks_List (ground truth)
    - StudentFiducials (student submission)
"""

import numpy as np

# ── Ground truth (from burn_screws.py output) ────────────────────────────────
GROUND_TRUTH = {
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

# ── Load student fiducials ───────────────────────────────────────────────────
studentNode = slicer.util.getNode("StudentFiducials")
errors = []

print("Fiducial Localisation Error (FLE):")
print("-" * 45)
for i in range(studentNode.GetNumberOfControlPoints()):
    pos = [0.0, 0.0, 0.0]
    studentNode.GetNthControlPointPositionWorld(i, pos)
    label = studentNode.GetNthControlPointLabel(i)
    if label in GROUND_TRUTH:
        gt  = np.array(GROUND_TRUTH[label])
        err = np.linalg.norm(np.array(pos) - gt)
        errors.append(err)
        status = "PASS" if err < 2.0 else "REVIEW"
        print(f"  {label:6s}: {err:.2f} mm  [{status}]")
    else:
        print(f"  {label:6s}: label not found in ground truth")

print("-" * 45)
if errors:
    print(f"Mean FLE : {np.mean(errors):.2f} mm")
    print(f"Max  FLE : {np.max(errors):.2f} mm")
    print(f"RMS  FLE : {np.sqrt(np.mean(np.array(errors)**2)):.2f} mm")
    print(f"Points   : {len(errors)}/9")
