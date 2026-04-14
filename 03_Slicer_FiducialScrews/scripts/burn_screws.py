"""
burn_screws.py
==============
Simulates bone-anchored fiducial screw signals in a T1w MRI volume.

Usage:
    Run in 3D Slicer Python Interactor (View → Python Interactor)
    Requires: FiducialMarks_List markup node and SkullModel model node
    Target volume: MRBrainTumor1

Author: [Your Name]
Repository: RoboticStereotacticBrainBiopsy
"""

import numpy as np
import vtk

# ── Configuration ────────────────────────────────────────────────────────────
MRI_NODE_NAME      = "MRBrainTumor1"
MARKUPS_NODE_NAME  = "FiducialMarks_List"

SCREW_INTENSITY    = 900     # Signal intensity (above max tissue ~695)
SCREW_RADIUS_MM    = 0.75    # Cylinder radius in mm (1.5mm diameter)
SCREW_LENGTH_MM    = 12.0    # Total shaft length in mm
PROTRUSION_MM      = 3.0     # mm protruding above skull surface
N_DEPTH_SAMPLES    = 120     # Sampling density along shaft axis
N_RING_SAMPLES     = 16      # Sampling density around circumference
N_RADIAL_SAMPLES   = 6       # Sampling density across disc radius

# Brain center for inward normal computation (MRI volume midpoint)
BRAIN_CENTER       = np.array([0.0, 0.0, 1.0])

# ── Step 1: Clear any previous burns ────────────────────────────────────────
mriNode  = slicer.util.getNode(MRI_NODE_NAME)
mriArray = slicer.util.arrayFromVolume(mriNode)
prevBurned = np.sum(mriArray >= SCREW_INTENSITY - 1)
if prevBurned > 0:
    mriArray[mriArray >= SCREW_INTENSITY - 1] = 0
    print(f"Cleared {prevBurned} voxels from previous burn.")
print(f"Volume shape: {mriArray.shape}  Max: {mriArray.max():.1f}")

# ── Step 2: Load fiducial positions and compute inward normals ───────────────
markupsNode = slicer.util.getNode(MARKUPS_NODE_NAME)
screwData   = []

for i in range(markupsNode.GetNumberOfControlPoints()):
    pos = [0.0, 0.0, 0.0]
    markupsNode.GetNthControlPointPositionWorld(i, pos)
    label  = markupsNode.GetNthControlPointLabel(i)
    pos    = np.array(pos)
    inward = BRAIN_CENTER - pos
    inward = inward / np.linalg.norm(inward)
    screwData.append((label, pos, inward))

print(f"Loaded {len(screwData)} fiducial positions.")

# ── Step 3: Get RAS-to-IJK transform ────────────────────────────────────────
rasToIJK = vtk.vtkMatrix4x4()
mriNode.GetRASToIJKMatrix(rasToIJK)

# ── Step 4: Burn each screw ──────────────────────────────────────────────────
screwCentroids = []
totalWritten   = 0

for label, pos, inward in screwData:

    # Start OUTSIDE skull surface (protrusion)
    startPos = pos + (-inward) * PROTRUSION_MM
    centroid  = startPos + inward * (SCREW_LENGTH_MM / 2.0)
    screwCentroids.append((label, centroid))

    # Local coordinate frame perpendicular to inward normal
    arb = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(inward, arb)) > 0.9:
        arb = np.array([0.0, 1.0, 0.0])
    perp1 = np.cross(inward, arb);  perp1 /= np.linalg.norm(perp1)
    perp2 = np.cross(inward, perp1)

    voxelsWritten = 0
    for depth in np.linspace(0, SCREW_LENGTH_MM, N_DEPTH_SAMPLES):
        axisPoint = startPos + inward * depth
        for r in np.linspace(0, SCREW_RADIUS_MM, N_RADIAL_SAMPLES):
            nTheta = max(1, int(N_RING_SAMPLES * r / SCREW_RADIUS_MM))
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

# ── Step 5: Push back and refresh display ───────────────────────────────────
slicer.util.updateVolumeFromArray(mriNode, mriArray)
mriNode.Modified()
print(f"\nTotal voxels written : {totalWritten}")
print(f"Max value after burn : {mriArray.max():.1f}")

displayNode = mriNode.GetVolumeDisplayNode()
displayNode.SetAutoWindowLevel(0)
displayNode.SetWindow(600)
displayNode.SetLevel(300)
slicer.util.setSliceViewerLayers(background=mriNode, fit=True)

center = screwCentroids[4][1]
slicer.modules.markups.logic().JumpSlicesToLocation(
    center[0], center[1], center[2], True)
print(f"Jumped to F_2-2: {[round(c,1) for c in center]}")
print("Done.")
