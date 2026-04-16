"""
CT_Alignment_Interactive.py
============================
Interactive script to align a synthetic CT volume to the original MRI
after ModalityConverter processing.

Usage:
    Copy-paste into 3D Slicer Python Interactor (View -> Python Interactor)
    Follow the prompts step by step.

Repository: RoboticStereotacticBrainBiopsy / 02_Slicer_MRI_to_CT
"""

import numpy as np
import vtk
import qt

def printSep(title=""):
    print("\n" + "="*55)
    if title:
        print(f"  {title}")
        print("="*55)

def askVolumeName(prompt):
    """Ask user to enter a volume name. Returns None if cancelled — safe, no crash."""
    while True:
        dialog = qt.QInputDialog()
        dialog.setWindowTitle("CT Alignment — Volume Selection")
        dialog.setLabelText(prompt)
        dialog.setTextValue("")
        ok = dialog.exec_()
        if not ok:
            print("  Cancelled by user.")
            return None
        name = dialog.textValue().strip()
        if name == "":
            qt.QMessageBox.warning(None, "Empty name",
                "Please enter a volume name.")
            continue
        try:
            node = slicer.util.getNode(name)
            print(f"  Found: '{node.GetName()}' {node.GetImageData().GetDimensions()}")
            return name
        except:
            print(f"  NOT FOUND: '{name}'")
            print("  Available volumes:")
            for n in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
                print(f"    - '{n.GetName()}'")
            qt.QMessageBox.warning(None, "Volume not found",
                f"Volume '{name}' not found.\n\nAvailable volumes:\n" +
                "\n".join(f"  - {n.GetName()}"
                for n in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")))

def askFloat(prompt, default=0.0):
    """Ask user for a float value. Returns 0.0 if cancelled — safe, no crash."""
    dialog = qt.QInputDialog()
    dialog.setWindowTitle("CT Alignment — Manual Correction")
    dialog.setLabelText(prompt)
    dialog.setTextValue(str(default))
    ok = dialog.exec_()
    if not ok:
        return 0.0
    try:
        return float(dialog.textValue())
    except:
        return 0.0

def askYesNo(title, message):
    """Ask a yes/no question. Returns False if window is closed."""
    result = qt.QMessageBox.question(
        None, title, message,
        qt.QMessageBox.Yes | qt.QMessageBox.No)
    return result == qt.QMessageBox.Yes

def setOverlay(mriNode, ctNode, opacity=0.5):
    slicer.util.setSliceViewerLayers(
        background=ctNode, foreground=mriNode,
        foregroundOpacity=opacity, fit=True)
    layoutManager = slicer.app.layoutManager()
    for name in ["Red", "Green", "Yellow"]:
        try:
            sliceLogic = layoutManager.sliceWidget(name).sliceLogic()
            sliceLogic.GetSliceCompositeNode().SetForegroundOpacity(opacity)
        except: pass

def setBoneWindow(ctNode):
    displayNode = ctNode.GetVolumeDisplayNode()
    displayNode.SetWindow(1500)
    displayNode.SetLevel(400)

def getIJKtoRAS(node):
    m = vtk.vtkMatrix4x4()
    node.GetIJKToRASMatrix(m)
    return m

def jumpToCenter(fallbackS=0.0):
    try:
        markupsNode = slicer.util.getNode("FiducialMarks_List")
        pos = [0.0, 0.0, 0.0]
        markupsNode.GetNthControlPointPositionWorld(4, pos)
        slicer.modules.markups.logic().JumpSlicesToLocation(
            pos[0], pos[1], pos[2], True)
        print(f"  Jumped to F_2-2: S={pos[2]:.1f}mm")
    except:
        slicer.modules.markups.logic().JumpSlicesToLocation(
            0, 0, fallbackS, True)
        print(f"  Jumped to S={fallbackS:.1f}mm")

def applyTransform(ctNode, offset_R=0.0, offset_A=0.0, offset_S=0.0,
                   transformName="CT_Alignment_Transform"):
    try:
        transformNode = slicer.util.getNode(transformName)
        matrix = vtk.vtkMatrix4x4()
        transformNode.GetMatrixTransformToParent(matrix)
        matrix.SetElement(0, 3, matrix.GetElement(0, 3) + offset_R)
        matrix.SetElement(1, 3, matrix.GetElement(1, 3) + offset_A)
        matrix.SetElement(2, 3, matrix.GetElement(2, 3) + offset_S)
        transformNode.SetMatrixTransformToParent(matrix)
    except:
        transformNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode", transformName)
        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        matrix.SetElement(0, 3, offset_R)
        matrix.SetElement(1, 3, offset_A)
        matrix.SetElement(2, 3, offset_S)
        transformNode.SetMatrixTransformToParent(matrix)
    ctNode.SetAndObserveTransformNodeID(transformNode.GetID())
    R = matrix.GetElement(0, 3)
    A = matrix.GetElement(1, 3)
    S = matrix.GetElement(2, 3)
    print(f"  Current offsets — R:{R:.1f}  A:{A:.1f}  S:{S:.1f} mm")
    return transformNode

def getTransformOffsets(transformName="CT_Alignment_Transform"):
    try:
        transformNode = slicer.util.getNode(transformName)
        matrix = vtk.vtkMatrix4x4()
        transformNode.GetMatrixTransformToParent(matrix)
        return (matrix.GetElement(0, 3),
                matrix.GetElement(1, 3),
                matrix.GetElement(2, 3))
    except:
        return (0.0, 0.0, 0.0)

def computeAutoAlignment(mriNode, ctNode,
                         mriThreshold=300, ctThreshold=200, fineTuneMM=6.0):
    mriArray     = slicer.util.arrayFromVolume(mriNode)
    ctArray      = slicer.util.arrayFromVolume(ctNode)
    mriSpacing   = mriNode.GetSpacing()[2]
    ctSpacing    = ctNode.GetSpacing()[2]
    mri_S_origin = getIJKtoRAS(mriNode).MultiplyPoint([0,0,0,1])[2]
    ct_S_origin  = getIJKtoRAS(ctNode).MultiplyPoint([0,0,0,1])[2]
    mri_slices   = [(k, int(np.sum(mriArray[k] > mriThreshold)))
                    for k in range(mriArray.shape[0])]
    ct_slices    = [(k, int(np.sum(ctArray[k]  > ctThreshold)))
                    for k in range(ctArray.shape[0])]
    mri_total    = sum(v for _, v in mri_slices)
    ct_total     = sum(v for _, v in ct_slices)
    mri_centroid_K = sum(k*v for k,v in mri_slices) / mri_total
    ct_centroid_K  = sum(k*v for k,v in ct_slices)  / ct_total
    mri_centroid_S = mri_S_origin + mri_centroid_K * mriSpacing
    ct_centroid_S  = ct_S_origin  + ct_centroid_K  * ctSpacing
    coarse = mri_centroid_S - ct_centroid_S
    total  = coarse + fineTuneMM
    print(f"  MRI tissue centroid : S = {mri_centroid_S:.1f} mm")
    print(f"  CT  bone centroid   : S = {ct_centroid_S:.1f} mm")
    print(f"  Coarse offset       : {coarse:.1f} mm")
    print(f"  Fine-tune added     : {fineTuneMM:+.1f} mm")
    print(f"  Total S offset      : {total:.1f} mm")
    return total

# ─────────────────────────────────────────────────────────────────────────────
# MAIN WORKFLOW — wrapped in try/except so Cancel never crashes Slicer
# ─────────────────────────────────────────────────────────────────────────────
try:

    printSep("CT ALIGNMENT TOOL")
    print("""
This script aligns the synthetic CT (from ModalityConverter)
to the original MRI. The ModalityConverter preprocessing pads
the volume to 256x256x256, shifting the CT anatomy upward in
S by ~100mm. This script corrects that automatically, then
lets you fine-tune manually if needed.

PREREQUISITE: ModalityConverter has already been run.
You can press Cancel at any dialog to abort safely.
""")

    # STEP 1 — Select volumes
    printSep("STEP 1 — Select Volumes")
    print("Available volumes in scene:")
    for n in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
        print(f"  - '{n.GetName()}'")

    mriName = askVolumeName(
        "Enter the name of the ORIGINAL MRI volume\n"
        "(T1w MRI with simulated screws):")
    if mriName is None:
        print("\nScript aborted by user at Step 1 (MRI selection).")
        print("Slicer is unaffected — run the script again when ready.")
    else:
        ctName = askVolumeName(
            "Enter the name of the SYNTHETIC CT volume\n"
            "(output from ModalityConverter):")
        if ctName is None:
            print("\nScript aborted by user at Step 1 (CT selection).")
            print("Slicer is unaffected — run the script again when ready.")
        else:
            mriNode = slicer.util.getNode(mriName)
            ctNode  = slicer.util.getNode(ctName)
            printSep()
            print(f"  MRI : {mriNode.GetName()}  {mriNode.GetImageData().GetDimensions()}")
            print(f"  CT  : {ctNode.GetName()}   {ctNode.GetImageData().GetDimensions()}")

            # STEP 2 — Auto-alignment
            printSep("STEP 2 — Automatic Alignment")
            print("Computing S-axis offset from bone/tissue centroids...")
            try:
                old = slicer.util.getNode("CT_Alignment_Transform")
                slicer.mrmlScene.RemoveNode(old)
                print("  Removed previous transform.")
            except: pass

            autoOffsetS = computeAutoAlignment(mriNode, ctNode,
                mriThreshold=300, ctThreshold=200, fineTuneMM=6.0)
            applyTransform(ctNode, offset_S=autoOffsetS)
            print("\n  Automatic alignment applied.")

            # STEP 3 — Visual verification setup
            printSep("STEP 3 — Visual Verification")
            print("""
Overlay view:
  BACKGROUND : Synthetic CT  (bone = bright white)
  FOREGROUND : Original MRI  (50% blend)

HOW TO VERIFY:
  Check all 3 views (axial, coronal, sagittal):
  1. CT skull ring (bright white) overlaps MRI skull ring
  2. Fiducial markers sit ON the bone surface
  3. Screw shafts visible in sagittal at correct position
""")
            setBoneWindow(ctNode)
            setOverlay(mriNode, ctNode, opacity=0.5)
            jumpToCenter(fallbackS=-6.0)

            # STEP 4 — Manual fine-tuning loop
            printSep("STEP 4 — Manual Fine-Tuning")
            aligned   = False
            iteration = 0

            while not aligned:
                iteration += 1
                R, A, S = getTransformOffsets()
                print(f"\n  Iteration {iteration} — offsets: "
                      f"R:{R:.1f}  A:{A:.1f}  S:{S:.1f} mm")

                aligned = askYesNo(
                    "CT Alignment — Verification",
                    "Check all 3 slice views.\n\n"
                    "Does the CT skull ring (bright white) correctly\n"
                    "overlap the MRI skull ring (grey)?\n\n"
                    "Axial    : skull ring shapes match\n"
                    "Coronal  : skull outline matches\n"
                    "Sagittal : markers sit on bone surface\n\n"
                    "Is the alignment correct?"
                )

                if aligned:
                    print("  Alignment confirmed.")
                    break

                print("  Adjustment needed.")
                delta_S = askFloat(
                    "S-axis (Superior / Inferior):\n\n"
                    "+mm = CT moves UP   (if markers are below bone)\n"
                    "-mm = CT moves DOWN (if markers are above bone)\n\n"
                    "Suggested step: ±2mm\n\n"
                    "Enter S correction (mm):",
                    default=2.0)
                delta_R = askFloat(
                    "R-axis (Right / Left) — usually 0:\n\n"
                    "+mm = CT moves RIGHT\n"
                    "-mm = CT moves LEFT\n\n"
                    "Enter R correction (mm):",
                    default=0.0)
                delta_A = askFloat(
                    "A-axis (Anterior / Posterior) — usually 0:\n\n"
                    "+mm = CT moves ANTERIOR\n"
                    "-mm = CT moves POSTERIOR\n\n"
                    "Enter A correction (mm):",
                    default=0.0)

                applyTransform(ctNode,
                               offset_R=delta_R,
                               offset_A=delta_A,
                               offset_S=delta_S)
                setOverlay(mriNode, ctNode, opacity=0.5)
                jumpToCenter(fallbackS=-6.0)
                print("  View updated — check alignment again.")

            # STEP 5 — Harden
            printSep("STEP 5 — Finalise")
            harden = askYesNo(
                "CT Alignment — Finalise",
                "Harden the transform?\n\n"
                "This permanently bakes the correction into the CT\n"
                "so it exports correctly to Unity.\n\n"
                "Recommended: YES\n\n"
                "Harden now?"
            )

            if harden:
                ctNode.HardenTransform()
                newName = ctName.replace("_NotAligned", "_Aligned")
                if newName == ctName:
                    newName = ctName + "_Aligned"
                ctNode.SetName(newName)

                ijkToRAS = vtk.vtkMatrix4x4()
                ctNode.GetIJKToRASMatrix(ijkToRAS)
                dims    = ctNode.GetImageData().GetDimensions()
                corner0 = ijkToRAS.MultiplyPoint([0, 0, 0, 1])
                cornerN = ijkToRAS.MultiplyPoint([dims[0], dims[1], dims[2], 1])

                printSep("ALIGNMENT COMPLETE")
                print(f"""
  Volume renamed to : '{ctNode.GetName()}'
  CT  S range       : {round(corner0[2],1)} to {round(cornerN[2],1)} mm
  MRI S range       : -77.7 to +79.1 mm

  Next step:
    Modules -> Segment Editor -> segment skull from CT
                """)
            else:
                printSep("TRANSFORM NOT HARDENED")
                print("""
  Transform 'CT_Alignment_Transform' remains active.
  Run this script again and choose YES to harden when ready.
                """)

except Exception as e:
    print(f"\nUnexpected error: {e}")
    print("Slicer is unaffected. Run the script again.")
    import traceback
    traceback.print_exc()
