"""
align_CT_to_MRI.py
==================
Interactive CT-to-MRI alignment — Hybrid registration:
  1. Coarse: Intensity centroid heuristic  (~100mm S correction, fast)
  2. Fine:   SimpleITK Mutual Information  (sub-mm refinement)

Non-modal panel — Slicer views remain fully interactive throughout.

Usage:
    Paste into 3D Slicer Python Interactor (View -> Python Interactor)

Repository: RoboticStereotacticBrainBiopsy / 02_Slicer_MRI_to_CT
"""

import numpy as np
import vtk
import qt
import SimpleITK as sitk
import sitkUtils

# ── Global state ──────────────────────────────────────────────────────────────
_state = {
    "mriNode":       None,
    "ctNode":        None,
    "transformNode": None,
    "panel":         None,
    "animTimer":     None,
    "animFrame":     [0],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def printSep(title=""):
    print("\n" + "="*55)
    if title:
        print(f"  {title}")
        print("="*55)

def getAvailableVolumeNames():
    return [n.GetName()
            for n in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")]

def setOverlay(mriNode, ctNode, opacity=0.5):
    slicer.util.setSliceViewerLayers(
        background=ctNode, foreground=mriNode,
        foregroundOpacity=opacity, fit=True)
    for name in ["Red", "Green", "Yellow"]:
        try:
            lm = slicer.app.layoutManager()
            sl = lm.sliceWidget(name).sliceLogic()
            sl.GetSliceCompositeNode().SetForegroundOpacity(opacity)
        except: pass

def setBoneWindow(ctNode):
    dn = ctNode.GetVolumeDisplayNode()
    dn.SetWindow(1500)
    dn.SetLevel(400)

def jumpToFiducialCenter(fallbackS=0.0):
    try:
        node = slicer.util.getNode("FiducialMarks_List")
        pos = [0.0, 0.0, 0.0]
        node.GetNthControlPointPositionWorld(4, pos)
        slicer.modules.markups.logic().JumpSlicesToLocation(
            pos[0], pos[1], pos[2], True)
        print(f"  Jumped to F_2-2: S={pos[2]:.1f}mm")
    except:
        slicer.modules.markups.logic().JumpSlicesToLocation(
            0, 0, fallbackS, True)

def applyOffset(ctNode, tR, tA, tS,
                transformName="CT_Alignment_Transform"):
    try:
        old = slicer.util.getNode(transformName)
        slicer.mrmlScene.RemoveNode(old)
    except: pass
    matrix = vtk.vtkMatrix4x4()
    matrix.Identity()
    matrix.SetElement(0, 3, tR)
    matrix.SetElement(1, 3, tA)
    matrix.SetElement(2, 3, tS)
    tn = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLLinearTransformNode", transformName)
    tn.SetMatrixTransformToParent(matrix)
    ctNode.SetAndObserveTransformNodeID(tn.GetID())
    _state["transformNode"] = tn
    return tn

def removeTransform():
    """Remove transform from CT node — cancels alignment."""
    ctNode = _state["ctNode"]
    if ctNode:
        ctNode.SetAndObserveTransformNodeID(None)
    tn = _state["transformNode"]
    if tn:
        try: slicer.mrmlScene.RemoveNode(tn)
        except: pass
    _state["transformNode"] = None

def addOffset(delta_R=0.0, delta_A=0.0, delta_S=0.0):
    tn = _state["transformNode"]
    if tn is None: return
    m = vtk.vtkMatrix4x4()
    tn.GetMatrixTransformToParent(m)
    m.SetElement(0, 3, m.GetElement(0, 3) + delta_R)
    m.SetElement(1, 3, m.GetElement(1, 3) + delta_A)
    m.SetElement(2, 3, m.GetElement(2, 3) + delta_S)
    tn.SetMatrixTransformToParent(m)

def getCurrentOffsets():
    tn = _state["transformNode"]
    if tn is None: return 0.0, 0.0, 0.0
    m = vtk.vtkMatrix4x4()
    tn.GetMatrixTransformToParent(m)
    return m.GetElement(0,3), m.GetElement(1,3), m.GetElement(2,3)

# ── Animation helpers ─────────────────────────────────────────────────────────

_SPINNER_FRAMES = [
    "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
]

def startAnimation(label, prefix=""):
    """Start a spinner animation on a QLabel using QTimer."""
    stopAnimation()
    _state["animFrame"][0] = 0
    timer = qt.QTimer()
    def tick():
        f = _state["animFrame"][0]
        label.setText(f"{prefix}  {_SPINNER_FRAMES[f % len(_SPINNER_FRAMES)]}")
        _state["animFrame"][0] = f + 1
    timer.timeout.connect(tick)
    timer.start(100)   # update every 100ms
    _state["animTimer"] = timer

def stopAnimation():
    """Stop the spinner animation."""
    timer = _state.get("animTimer")
    if timer:
        try: timer.stop()
        except: pass
    _state["animTimer"] = None

# ── Stage 1: Centroid coarse alignment ───────────────────────────────────────

def computeCentroidOffset(mriNode, ctNode,
                          mriThreshold=300, ctThreshold=200):
    print("  Stage 1: Centroid heuristic (coarse S correction)")
    mriArray = slicer.util.arrayFromVolume(mriNode)
    ctArray  = slicer.util.arrayFromVolume(ctNode)
    mriSpacing = mriNode.GetSpacing()[2]
    ctSpacing  = ctNode.GetSpacing()[2]
    ijkMRI = vtk.vtkMatrix4x4(); mriNode.GetIJKToRASMatrix(ijkMRI)
    ijkCT  = vtk.vtkMatrix4x4(); ctNode.GetIJKToRASMatrix(ijkCT)
    mriS0  = ijkMRI.MultiplyPoint([0,0,0,1])[2]
    ctS0   = ijkCT.MultiplyPoint([0,0,0,1])[2]
    mriSlices = [(k, int(np.sum(mriArray[k] > mriThreshold)))
                 for k in range(mriArray.shape[0])]
    ctSlices  = [(k, int(np.sum(ctArray[k]  > ctThreshold)))
                 for k in range(ctArray.shape[0])]
    mriTotal = sum(v for _,v in mriSlices)
    ctTotal  = sum(v for _,v in ctSlices)
    mriCentS = mriS0 + (sum(k*v for k,v in mriSlices)/mriTotal) * mriSpacing
    ctCentS  = ctS0  + (sum(k*v for k,v in ctSlices) /ctTotal)  * ctSpacing
    offsetS  = mriCentS - ctCentS
    print(f"  MRI centroid S : {mriCentS:.1f} mm")
    print(f"  CT  centroid S : {ctCentS:.1f} mm")
    print(f"  Coarse S offset: {offsetS:.1f} mm")
    return offsetS

# ── Stage 2: Mutual Information fine alignment ────────────────────────────────

def runMutualInformationRefinement(mriNode, ctNode, initialOffsetS,
                                   animLabel=None):
    print("\n  Stage 2: Mutual Information refinement")
    print(f"  Initial S offset: {initialOffsetS:.1f} mm")

    fixed  = sitk.Cast(sitkUtils.PullVolumeFromSlicer(mriNode), sitk.sitkFloat32)
    moving = sitk.Cast(sitkUtils.PullVolumeFromSlicer(ctNode),  sitk.sitkFloat32)

    initTransform = sitk.TranslationTransform(3)
    initTransform.SetOffset((0.0, 0.0, -initialOffsetS))

    reg = sitk.ImageRegistrationMethod()
    reg.SetMetricAsMattesMutualInformation(numberOfHistogramBins=64)
    reg.SetMetricSamplingStrategy(reg.RANDOM)
    reg.SetMetricSamplingPercentage(0.15)
    reg.SetInterpolator(sitk.sitkLinear)
    reg.SetOptimizerAsRegularStepGradientDescent(
        learningRate=2.0, minStep=0.001,
        numberOfIterations=300, gradientMagnitudeTolerance=1e-8)
    reg.SetOptimizerScalesFromPhysicalShift()
    reg.SetInitialTransform(initTransform, inPlace=False)
    reg.SetShrinkFactorsPerLevel([2, 1])
    reg.SetSmoothingSigmasPerLevel([1, 0])
    reg.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()

    counter = [0]
    def onIter():
        counter[0] += 1
        if counter[0] % 30 == 0:
            print(f"  Iter {counter[0]:3d} | metric = {reg.GetMetricValue():.5f}")
        slicer.app.processEvents()   # keep UI responsive

    reg.AddCommand(sitk.sitkIterationEvent, onIter)
    finalTransform = reg.Execute(fixed, moving)

    params = finalTransform.GetParameters()
    print(f"\n  Final metric   : {reg.GetMetricValue():.6f}")
    print(f"  Stop condition : {reg.GetOptimizerStopConditionDescription()}")

    # LPS → RAS, negate to get correction direction
    finalR = params[0]
    finalA = params[1]
    finalS = -params[2]
    print(f"  Applied offset (RAS): R={finalR:.2f}  A={finalA:.2f}  S={finalS:.2f}")
    return finalR, finalA, finalS

# ── Full hybrid pipeline ──────────────────────────────────────────────────────

def runHybridRegistration(mriNode, ctNode, animLabel=None):
    printSep("Hybrid Registration")
    coarseS = computeCentroidOffset(mriNode, ctNode)
    finalR, finalA, finalS = runMutualInformationRefinement(
        mriNode, ctNode, initialOffsetS=coarseS, animLabel=animLabel)
    print(f"\n  Final total (RAS): R={finalR:.2f}  A={finalA:.2f}  S={finalS:.2f} mm")
    return finalR, finalA, finalS

# ── Non-modal UI Panel ────────────────────────────────────────────────────────

def buildPanel():
    panel = qt.QWidget()
    panel.setWindowTitle("CT ↔ MRI Alignment Tool")
    panel.setWindowFlags(qt.Qt.Window | qt.Qt.WindowStaysOnTopHint)
    panel.resize(430, 700)
    panel.setStyleSheet("""
        QWidget    { background:#1e1e2e; color:#cdd6f4;
                     font-family:Arial; font-size:12px; }
        QGroupBox  { border:1px solid #45475a; border-radius:6px;
                     margin-top:8px; padding:8px;
                     color:#89b4fa; font-weight:bold; }
        QGroupBox::title { subcontrol-origin:margin; left:8px; padding:0 4px; }
        QPushButton { background:#313244; border:1px solid #45475a;
                      border-radius:4px; padding:6px 12px; color:#cdd6f4; }
        QPushButton:hover  { background:#45475a; }
        QPushButton:pressed{ background:#585b70; }
        QPushButton:disabled { background:#1e1e2e; color:#585b70;
                               border-color:#313244; }
        QComboBox  { background:#313244; border:1px solid #45475a;
                     border-radius:4px; padding:4px; color:#cdd6f4; }
        QComboBox QAbstractItemView { background:#313244; color:#cdd6f4; }
        QSlider::groove:horizontal  { background:#45475a; height:6px;
                                      border-radius:3px; }
        QSlider::handle:horizontal  { background:#89b4fa; width:16px;
                                      height:16px; margin:-5px 0;
                                      border-radius:8px; }
        QSlider::sub-page:horizontal{ background:#89b4fa; border-radius:3px; }
        QDoubleSpinBox { background:#313244; border:1px solid #45475a;
                         border-radius:4px; padding:4px; color:#cdd6f4; }
    """)

    layout = qt.QVBoxLayout(panel)
    layout.setSpacing(8)
    layout.setContentsMargins(10, 10, 10, 10)

    # Title
    title = qt.QLabel("CT ↔ MRI Alignment Tool")
    title.setStyleSheet("font-size:15px; font-weight:bold; color:#89b4fa;")
    title.setAlignment(qt.Qt.AlignCenter)
    layout.addWidget(title)
    sub = qt.QLabel("Hybrid: Centroid coarse  +  Mutual Information fine\n"
                    "Slicer views remain fully interactive throughout.")
    sub.setStyleSheet("font-size:10px; color:#6c7086;")
    sub.setAlignment(qt.Qt.AlignCenter)
    sub.setWordWrap(True)
    layout.addWidget(sub)

    # Step 1 — Volumes
    grp1 = qt.QGroupBox("Step 1 — Select Volumes")
    frm1 = qt.QFormLayout(grp1)
    volumes = getAvailableVolumeNames()
    mriCombo = qt.QComboBox()
    ctCombo  = qt.QComboBox()
    for v in volumes:
        mriCombo.addItem(v)
        ctCombo.addItem(v)
    for i, v in enumerate(volumes):
        vl = v.lower()
        if "screw" in vl or ("mri" in vl and "ct" not in vl):
            mriCombo.setCurrentIndex(i)
        if "ct" in vl and ("not" in vl or "brain" in vl):
            ctCombo.setCurrentIndex(i)
    frm1.addRow("MRI — fixed image:", mriCombo)
    frm1.addRow("CT  — moving image:", ctCombo)
    layout.addWidget(grp1)

    # Step 2 — Registration
    grp2 = qt.QGroupBox("Step 2 — Automatic Registration")
    lay2 = qt.QVBoxLayout(grp2)
    lay2.addWidget(qt.QLabel(
        "Stage 1: Centroid heuristic → corrects ~100mm S offset\n"
        "Stage 2: Mutual Information → refines R, A, S simultaneously\n"
        "Takes 20–60 seconds. Slicer remains interactive."))

    btnRow = qt.QHBoxLayout()
    btnReg = qt.QPushButton("▶  Run Registration")
    btnReg.setStyleSheet(
        "background:#1e66f5; color:white; font-weight:bold; "
        "padding:8px; border-radius:4px; border:none;")
    btnRow.addWidget(btnReg)

    btnCancel = qt.QPushButton("✕  Cancel / Remove Transform")
    btnCancel.setStyleSheet(
        "background:#e64553; color:white; font-weight:bold; "
        "padding:8px; border-radius:4px; border:none;")
    btnCancel.setEnabled(False)
    btnRow.addWidget(btnCancel)
    lay2.addLayout(btnRow)

    # Animated status label
    statusLbl = qt.QLabel("Select volumes above and click Run.")
    statusLbl.setStyleSheet("color:#f38ba8; font-weight:bold; font-size:13px;")
    statusLbl.setAlignment(qt.Qt.AlignCenter)
    statusLbl.setWordWrap(True)
    lay2.addWidget(statusLbl)
    layout.addWidget(grp2)

    # Step 3 — Visual validation
    grp3 = qt.QGroupBox("Step 3 — Visual Validation")
    lay3 = qt.QVBoxLayout(grp3)
    lay3.addWidget(qt.QLabel(
        "Drag slider to blend CT and MRI.\n"
        "Skull rings should overlap in all 3 slice views."))
    row = qt.QHBoxLayout()
    row.addWidget(qt.QLabel("CT only"))
    opSlider = qt.QSlider(qt.Qt.Horizontal)
    opSlider.setRange(0, 100)
    opSlider.setValue(50)
    row.addWidget(opSlider)
    row.addWidget(qt.QLabel("MRI only"))
    lay3.addLayout(row)
    blendLbl = qt.QLabel("50% MRI / 50% CT")
    blendLbl.setStyleSheet("color:#89b4fa; font-size:11px;")
    blendLbl.setAlignment(qt.Qt.AlignCenter)
    lay3.addWidget(blendLbl)
    btnJump = qt.QPushButton("⊕  Jump to Fiducial Center (F_2-2)")
    lay3.addWidget(btnJump)
    layout.addWidget(grp3)

    # Step 4 — Fine-tune
    grp4 = qt.QGroupBox("Step 4 — Manual Fine-Tune (if needed)")
    grd4 = qt.QGridLayout(grp4)
    grd4.addWidget(qt.QLabel("S (Superior+  /  Inferior−):"), 0, 0)
    spinS = qt.QDoubleSpinBox()
    spinS.setRange(-30.0, 30.0); spinS.setSingleStep(0.5)
    spinS.setValue(0.0); spinS.setDecimals(1)
    grd4.addWidget(spinS, 0, 1)
    grd4.addWidget(qt.QLabel("R (Right+  /  Left−):"), 1, 0)
    spinR = qt.QDoubleSpinBox()
    spinR.setRange(-30.0, 30.0); spinR.setSingleStep(0.5)
    spinR.setValue(0.0); spinR.setDecimals(1)
    grd4.addWidget(spinR, 1, 1)
    grd4.addWidget(qt.QLabel("A (Anterior+  /  Posterior−):"), 2, 0)
    spinA = qt.QDoubleSpinBox()
    spinA.setRange(-30.0, 30.0); spinA.setSingleStep(0.5)
    spinA.setValue(0.0); spinA.setDecimals(1)
    grd4.addWidget(spinA, 2, 1)
    btnFine = qt.QPushButton("Apply Fine-Tune Offset")
    grd4.addWidget(btnFine, 3, 0, 1, 2)
    offsetLbl = qt.QLabel("Current total: R=0.0  A=0.0  S=0.0 mm")
    offsetLbl.setStyleSheet("color:#89dceb; font-size:11px;")
    grd4.addWidget(offsetLbl, 4, 0, 1, 2)
    layout.addWidget(grp4)

    # Step 5 — Finalise
    grp5 = qt.QGroupBox("Step 5 — Finalise")
    lay5 = qt.QVBoxLayout(grp5)
    btnHarden = qt.QPushButton("✓  Confirm Alignment & Harden Transform")
    btnHarden.setStyleSheet(
        "background:#40a02b; color:white; font-weight:bold; "
        "padding:8px; border-radius:4px; border:none;")
    lay5.addWidget(btnHarden)
    finalLbl = qt.QLabel("")
    finalLbl.setStyleSheet("color:#a6e3a1; font-weight:bold;")
    finalLbl.setWordWrap(True)
    lay5.addWidget(finalLbl)
    layout.addWidget(grp5)
    layout.addStretch()

    # ── Connections ───────────────────────────────────────────────────────────

    def onRegister():
        mriName = mriCombo.currentText
        ctName  = ctCombo.currentText
        if mriName == ctName:
            statusLbl.setStyleSheet("color:#f38ba8; font-weight:bold;")
            statusLbl.setText("ERROR: MRI and CT must be different volumes.")
            return
        try:
            mriNode = slicer.util.getNode(mriName)
            ctNode  = slicer.util.getNode(ctName)
        except Exception as e:
            statusLbl.setStyleSheet("color:#f38ba8; font-weight:bold;")
            statusLbl.setText(f"ERROR: {e}")
            return

        _state["mriNode"] = mriNode
        _state["ctNode"]  = ctNode

        # Disable buttons during registration
        btnReg.setEnabled(False)
        btnCancel.setEnabled(False)
        btnHarden.setEnabled(False)

        # Start spinner animation
        startAnimation(statusLbl, prefix="Computing")
        slicer.app.processEvents()

        try:
            finalR, finalA, finalS = runHybridRegistration(mriNode, ctNode,
                                                            animLabel=statusLbl)
            stopAnimation()
            applyOffset(ctNode, finalR, finalA, finalS)

            R, A, S = getCurrentOffsets()
            offsetLbl.setText(f"Current total: R={R:.1f}  A={A:.1f}  S={S:.1f} mm")
            setBoneWindow(ctNode)
            setOverlay(mriNode, ctNode, opacity=0.5)
            opSlider.setValue(50)
            jumpToFiducialCenter()

            statusLbl.setStyleSheet("color:#a6e3a1; font-weight:bold; font-size:13px;")
            statusLbl.setText(
                f"✓  Registration complete\n"
                f"R={R:.1f}  A={A:.1f}  S={S:.1f} mm\n"
                f"Use the slider below to verify alignment.")

            btnCancel.setEnabled(True)
            btnHarden.setEnabled(True)

        except Exception as e:
            stopAnimation()
            statusLbl.setStyleSheet("color:#f38ba8; font-weight:bold;")
            statusLbl.setText(f"ERROR: {e}")
            import traceback; traceback.print_exc()
        finally:
            btnReg.setEnabled(True)

    def onCancelTransform():
        removeTransform()
        offsetLbl.setText("Current total: R=0.0  A=0.0  S=0.0 mm")
        statusLbl.setStyleSheet("color:#f38ba8; font-weight:bold; font-size:13px;")
        statusLbl.setText("Transform removed — CT is back to original position.")
        finalLbl.setText("")
        btnCancel.setEnabled(False)
        btnHarden.setEnabled(False)
        # Restore CT-only view
        ctNode = _state["ctNode"]
        mriNode = _state["mriNode"]
        if ctNode and mriNode:
            setOverlay(mriNode, ctNode, opacity=0.0)
        print("  Transform removed — alignment cancelled.")

    def onOpacity(val):
        blendLbl.setText(f"{val}% MRI / {100-val}% CT")
        if _state["mriNode"] and _state["ctNode"]:
            setOverlay(_state["mriNode"], _state["ctNode"],
                       opacity=val/100.0)

    def onJump():
        jumpToFiducialCenter()

    def onFine():
        addOffset(delta_R=spinR.value,
                  delta_A=spinA.value,
                  delta_S=spinS.value)
        spinR.setValue(0.0); spinA.setValue(0.0); spinS.setValue(0.0)
        R, A, S = getCurrentOffsets()
        offsetLbl.setText(f"Current total: R={R:.1f}  A={A:.1f}  S={S:.1f} mm")
        if _state["mriNode"] and _state["ctNode"]:
            setOverlay(_state["mriNode"], _state["ctNode"],
                       opacity=opSlider.value/100.0)

    def onHarden():
        ctNode = _state["ctNode"]
        if ctNode is None:
            finalLbl.setText("Run registration first.")
            return
        try:
            ctNode.HardenTransform()
            oldName = ctNode.GetName()
            newName = oldName.replace("_NotAligned", "_Aligned")
            if newName == oldName:
                newName = oldName + "_Aligned"
            ctNode.SetName(newName)
            ijkToRAS = vtk.vtkMatrix4x4()
            ctNode.GetIJKToRASMatrix(ijkToRAS)
            dims = ctNode.GetImageData().GetDimensions()
            c0 = ijkToRAS.MultiplyPoint([0,0,0,1])
            cN = ijkToRAS.MultiplyPoint([dims[0],dims[1],dims[2],1])
            finalLbl.setText(
                f"✓ Transform hardened.\n"
                f"Renamed: '{newName}'\n"
                f"CT S range: {round(c0[2],1)} to {round(cN[2],1)} mm\n"
                f"Ready for Module 03 — Segmentation.")
            btnCancel.setEnabled(False)
            btnHarden.setEnabled(False)
            printSep("ALIGNMENT COMPLETE")
            print(f"  Volume : '{newName}'")
            print(f"  CT S   : {round(c0[2],1)} to {round(cN[2],1)} mm")
        except Exception as e:
            finalLbl.setText(f"ERROR: {e}")

    btnReg.clicked.connect(onRegister)
    btnCancel.clicked.connect(onCancelTransform)
    opSlider.valueChanged.connect(onOpacity)
    btnJump.clicked.connect(onJump)
    btnFine.clicked.connect(onFine)
    btnHarden.clicked.connect(onHarden)

    # Disable harden until registration is done
    btnHarden.setEnabled(False)

    return panel

# ── Launch ────────────────────────────────────────────────────────────────────
try:
    printSep("CT ALIGNMENT TOOL — Hybrid Registration")
    print("Non-modal panel — Slicer views remain fully interactive.\n")
    try:
        if _state.get("panel") and _state["panel"] is not None:
            _state["panel"].close()
    except: pass
    stopAnimation()
    panel = buildPanel()
    panel.show()
    _state["panel"] = panel
    print("Panel open. Select volumes and click 'Run Registration'.")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback; traceback.print_exc()
