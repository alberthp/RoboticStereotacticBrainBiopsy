"""
BiopsyToolOpenIGT.py
=====================

A Scripted Loadable Module for 3D Slicer that consolidates the
runtime OpenIGTLink bridge between Slicer and Unity for the robotic
stereotactic brain biopsy educational project.

Features
--------
1. Configurable OpenIGTLink server (default port 18944) that listens
   for incoming Unity client connections. Start/Stop buttons.
2. Loads a pre-calibrated BiopsyTool model (tip at origin, long axis
   +Y, units mm) and attaches it to the ToolTipSphere transform node
   so Unity TRANSFORM messages drive it in real time.
3. Receives STRING messages from Unity carrying tool-vs-VirtualFixture
   collision state ("COLLIDING" / "FREE") and recolours the
   VirtualFixture model in red when colliding, restoring its original
   colour when free. If the VirtualFixture model does NOT exist, the
   recolour is silently skipped -- no crash.
4. Live monitoring panel: 4x4 matrix, world-space (RAS) tip position,
   current collision state.

Installation
------------
This module is intended to be loaded as a Slicer extension via the
Extension Wizard or via "Additional module paths". See the README
in this folder for step-by-step instructions.

Scene-graph contract
--------------------
The module reads and creates a small set of MRML nodes by *name*.
External scripts (or anyone debugging via the Python Console) can
rely on these names being stable:

    ToolTipSphere    vtkMRMLLinearTransformNode    target for incoming TRANSFORM
    BiopsyTool       vtkMRMLModelNode              loaded model, parented to ToolTipSphere
    IGTLServer       vtkMRMLIGTLConnectorNode      the listening connector
    ToolCollision    vtkMRMLTextNode               target for incoming STRING
    VirtualFixture   vtkMRMLModelNode              read-only; recoloured on collision

Author: Albert HP -- RoboticStereotacticBrainBiopsy educational project
"""

import os
import slicer
import qt
import vtk
import ctk
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
)


# ════════════════════════════════════════════════════════════════════
# MODULE CLASS -- registers metadata with Slicer
# ════════════════════════════════════════════════════════════════════

class BiopsyToolOpenIGT(ScriptedLoadableModule):
    """
    Registers the module with Slicer. The metadata defined here is
    what appears in the Modules menu, in the module help, and in any
    auto-generated extension manifests.
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)

        # ----- Metadata visible to the user -----
        parent.title = "BiopsyTool OpenIGT Bridge"
        parent.categories = ["IGT"]

        # parent.dependencies refers to OTHER scripted modules whose
        # Python code must be loaded BEFORE this one. It is NOT the
        # extension-level dependency list. We don't depend on any
        # other scripted module, so the list is empty.
        # (The dependency on SlicerOpenIGTLink is an EXTENSION-level
        # dependency, declared in the top-level CMakeLists.txt as
        # EXTENSION_DEPENDS.)
        parent.dependencies = []

        parent.contributors = ["Albert HP (UPF)"]
        parent.helpText = (
            "Runtime OpenIGTLink bridge between Slicer and Unity for "
            "the robotic stereotactic brain biopsy educational project. "
            "Receives the BiopsyTool pose (TRANSFORM) and collision "
            "state (STRING) from Unity, and visualises both in real "
            "time. Recolours the VirtualFixture model when the tool "
            "collides with it. See module README for setup details."
        )
        parent.acknowledgementText = (
            "Developed at UPF (Bioengineering degree) as part of the "
            "RoboticStereotacticBrainBiopsy course project."
        )


# ════════════════════════════════════════════════════════════════════
# WIDGET CLASS -- builds the GUI panel inside Slicer
# ════════════════════════════════════════════════════════════════════

class BiopsyToolOpenIGTWidget(ScriptedLoadableModuleWidget):
    """
    Builds the module's Qt panel that appears in Slicer's left-hand
    Modules area. Hosts the file picker, server controls, live data
    display, and collision state indicator.

    The widget delegates all non-UI work to BiopsyToolOpenIGTLogic so
    the GUI stays responsive and the logic is reusable from scripts.
    """

    # -- INITIALISATION --------------------------------------------

    def setup(self):
        """
        Called by Slicer when the module is first loaded OR when the
        user reloads it via the Extension Wizard. Builds the UI
        hierarchy from scratch each time, so any state from a
        previous instance is discarded -- only MRML nodes in the
        scene persist.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Logic instance -- holds all the non-UI state.
        self.logic = BiopsyToolOpenIGTLogic()

        # Live-monitoring state, kept on the widget because it is
        # purely UI-related (hashes, counters for the display).
        # Resetting these here guarantees a clean slate on reload.
        self.messageCounter = 0
        self.lastMatrixHash = 0
        self.previousServerState = 0

        # Last absolute path the user selected via the file dialog.
        # We try to auto-detect a reasonable default path relative
        # to the project layout so that pressing Load just works on
        # a fresh checkout. The user can still browse to a different
        # file at any time.
        self.modelPath = self._autoDetectModelPath()

        # Build each collapsible section in order.
        self._buildModelSection()
        self._buildServerSection()
        self._buildDataSection()
        self._buildCollisionSection()

        # Push everything to the top so the layout looks tidy
        # regardless of window height.
        self.layout.addStretch()

        # Periodic update timer (5 Hz) for server status + matrix
        # display. We use polling instead of MRML observers because
        # it is simpler and more robust across SlicerOpenIGTLink
        # versions, and 5 Hz is more than enough for a UI update.
        self.updateTimer = qt.QTimer()
        self.updateTimer.setInterval(200)
        self.updateTimer.timeout.connect(self._onTimerTick)

    def cleanup(self):
        """
        Called by Slicer when the module is unloaded (e.g. user
        switches to another module, or "Reload Module" is invoked).
        Stops the timer, stops the server, and removes the collision
        observer so no callbacks leak across reloads.

        MRML nodes are intentionally NOT removed -- the scene must
        survive a module reload.
        """
        try:
            self.updateTimer.stop()
        except Exception:
            pass
        self.logic.stopServer()
        self.logic.removeCollisionObserver()

    def _autoDetectModelPath(self):
        """
        Best-effort guess of the BiopsyTool_ready.stl location. Tries
        a few candidate paths relative to either the module folder or
        the project root. Returns "" if nothing matches, in which
        case the user must browse manually.
        """
        # Candidate locations to probe in order. The first existing
        # file wins. Editing this list does not break anything --
        # missing candidates are simply skipped.
        candidates = [
            # Repo root next to this module's parent (the typical
            # layout when the extension lives inside the project).
            os.path.normpath(os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "..",
                "data", "BiopsyTool_ready.stl"
            )),
            # Albert's local dev machine.
            r"F:\RoboticStereotacticBrainBiopsy\data\BiopsyTool_ready.stl",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return ""

    # -- UI CONSTRUCTION -------------------------------------------

    def _buildModelSection(self):
        """
        Section 1: select the pre-calibrated model file and attach
        it to ToolTipSphere.
        """
        box = ctk.ctkCollapsibleButton()
        box.text = "1. BiopsyTool Model (pre-calibrated)"
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        info = qt.QLabel(
            "Expects a calibrated file (tip at origin, long axis +Y, "
            "units mm). Generate with preprocess_biopsy_tool.py if needed."
        )
        info.setStyleSheet(
            "color: #555; font-size: 11px; padding: 4px; "
            "background-color: #f0f0f0; border-radius: 3px;"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # File picker row.
        pickRow = qt.QHBoxLayout()
        self.pathLabel = qt.QLabel(
            os.path.basename(self.modelPath)
            if self.modelPath else "(no file selected)"
        )
        self.pathLabel.setStyleSheet(
            "color: black; font-style: normal;" if self.modelPath
            else "color: gray; font-style: italic;"
        )
        browseBtn = qt.QPushButton("Browse...")
        browseBtn.clicked.connect(self._onBrowse)
        pickRow.addWidget(self.pathLabel, 1)
        pickRow.addWidget(browseBtn)
        layout.addLayout(pickRow)

        # Load button.
        self.loadBtn = qt.QPushButton("Load and attach to ToolTipSphere")
        self.loadBtn.setStyleSheet(
            "font-weight: bold; padding: 8px; "
            "background-color: #4a90d9; color: white;"
        )
        self.loadBtn.clicked.connect(self._onLoad)
        layout.addWidget(self.loadBtn)

        # Status label, updated after a load attempt.
        self.modelStatus = qt.QLabel("Status: waiting for file")
        self.modelStatus.setStyleSheet("color: gray;")
        layout.addWidget(self.modelStatus)

    def _buildServerSection(self):
        """
        Section 2: OpenIGTLink server controls (port, start, stop)
        and connection status.
        """
        box = ctk.ctkCollapsibleButton()
        box.text = "2. OpenIGTLink Server"
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        # Port input (defaults to 18944, the OpenIGTLink convention).
        portRow = qt.QHBoxLayout()
        portRow.addWidget(qt.QLabel("Port:"))
        self.portInput = qt.QSpinBox()
        self.portInput.setRange(1024, 65535)
        self.portInput.setValue(18944)
        portRow.addWidget(self.portInput)
        portRow.addStretch()
        layout.addLayout(portRow)

        # Start / Stop buttons.
        btnRow = qt.QHBoxLayout()
        self.startBtn = qt.QPushButton("Start server")
        self.startBtn.setStyleSheet(
            "color: white; background-color: #2a9d3a; "
            "font-weight: bold; padding: 8px;"
        )
        self.startBtn.clicked.connect(self._onStartServer)

        self.stopBtn = qt.QPushButton("Stop")
        self.stopBtn.setStyleSheet(
            "color: white; background-color: #d9534f; padding: 8px;"
        )
        self.stopBtn.clicked.connect(self._onStopServer)
        self.stopBtn.setEnabled(False)

        btnRow.addWidget(self.startBtn)
        btnRow.addWidget(self.stopBtn)
        layout.addLayout(btnRow)

        # Server status indicator (Off / Waiting / Connected).
        self.serverStatus = qt.QLabel("Stopped")
        self.serverStatus.setStyleSheet(
            "color: gray; font-weight: bold; font-size: 14px; padding: 5px;"
        )
        layout.addWidget(self.serverStatus)

        # Connection indicator (separate from server state).
        self.connectionStatus = qt.QLabel("No client connected")
        self.connectionStatus.setStyleSheet("color: gray; padding-left: 5px;")
        layout.addWidget(self.connectionStatus)

    def _buildDataSection(self):
        """
        Section 3: live display of the 4x4 TRANSFORM matrix and the
        computed world-space tip position.
        """
        box = ctk.ctkCollapsibleButton()
        box.text = "3. Live tool pose (TRANSFORM)"
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        self.msgCountLabel = qt.QLabel("Updates received: 0")
        self.msgCountLabel.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(self.msgCountLabel)

        layout.addWidget(qt.QLabel("Received ToolTipSphere matrix:"))
        self.matrixDisplay = qt.QTextEdit()
        self.matrixDisplay.setReadOnly(True)
        self.matrixDisplay.setMaximumHeight(110)
        font = qt.QFont("Courier", 10)
        self.matrixDisplay.setFont(font)
        self.matrixDisplay.setStyleSheet(
            "background-color: #f8f8f8; color: #000000; "
            "border: 1px solid #ccc;"
        )
        self.matrixDisplay.setText("(waiting for first message...)")
        layout.addWidget(self.matrixDisplay)

        layout.addWidget(qt.QLabel("World tip position:"))
        self.tipPositionLabel = qt.QLabel("RAS = (-, -, -)")
        self.tipPositionLabel.setStyleSheet(
            "font-family: Courier; font-size: 13px; padding: 8px; "
            "font-weight: bold; background-color: #f8f8f8; "
            "border: 1px solid #ccc; color: #2a9d3a;"
        )
        layout.addWidget(self.tipPositionLabel)

    def _buildCollisionSection(self):
        """
        Section 4: live display of the tool-vs-VirtualFixture
        collision state. Sent from Unity as an OpenIGT STRING message
        with device name "ToolCollision" and values "COLLIDING" /
        "FREE". The logic class also recolours the VirtualFixture in
        the 3D view (if present).
        """
        box = ctk.ctkCollapsibleButton()
        box.text = "4. Tool / VirtualFixture collision (STRING)"
        self.layout.addWidget(box)
        layout = qt.QVBoxLayout(box)

        info = qt.QLabel(
            "Unity sends 'COLLIDING' / 'FREE' strings via OpenIGTLink "
            "(device 'ToolCollision'). The VirtualFixture model is "
            "automatically recoloured when the state changes. If no "
            "VirtualFixture model exists in the scene, the colour "
            "change is silently skipped."
        )
        info.setStyleSheet(
            "color: #555; font-size: 11px; padding: 4px; "
            "background-color: #f0f0f0; border-radius: 3px;"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(qt.QLabel("Current state:"))
        self.collisionStatus = qt.QLabel("Unknown (no data yet)")
        self.collisionStatus.setStyleSheet(
            "color: #555; background-color: #f0f0f0; "
            "font-weight: bold; font-size: 14px; padding: 10px; "
            "border-radius: 4px;"
        )
        self.collisionStatus.setAlignment(qt.Qt.AlignCenter)
        layout.addWidget(self.collisionStatus)

        # VirtualFixture detection indicator (helps the user know
        # whether the recolour feature will fire at all).
        self.vfStatus = qt.QLabel("VirtualFixture: (not yet checked)")
        self.vfStatus.setStyleSheet("color: gray; padding-left: 5px;")
        layout.addWidget(self.vfStatus)

    # -- SECTION 1 HANDLERS ---------------------------------------

    def _onBrowse(self):
        """
        Open a file dialog for the user to select the calibrated
        model file. Uses slicer.util.mainWindow() as parent because
        self.parent may not be a usable QWidget in every Slicer
        version.
        """
        startDir = (
            os.path.dirname(self.modelPath) if self.modelPath else ""
        )
        path = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(),
            "Select the calibrated BiopsyTool model",
            startDir,
            "STL files (*.stl);;All 3D models (*.stl *.obj *.ply);;All files (*)",
        )
        if path:
            self.modelPath = os.path.normpath(path)
            self.pathLabel.setText(os.path.basename(self.modelPath))
            self.pathLabel.setStyleSheet(
                "color: black; font-style: normal;"
            )

    def _onLoad(self):
        """
        Delegate the model-load operation to the logic class and
        update the status label. All exceptions are caught and shown
        as a popup so the user doesn't have to look at the Console.
        """
        if not self.modelPath:
            slicer.util.errorDisplay("Please select a model file first.")
            return

        try:
            self.logic.loadAndAttachModel(self.modelPath)
            self.modelStatus.setText(
                f"OK -- {os.path.basename(self.modelPath)} loaded "
                f"and attached to ToolTipSphere"
            )
            self.modelStatus.setStyleSheet(
                "color: #2a9d3a; font-weight: bold;"
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            slicer.util.errorDisplay(f"Error loading model:\n{e}")
            self.modelStatus.setText(f"Error: {e}")
            self.modelStatus.setStyleSheet("color: red;")

    # -- SECTION 2 HANDLERS ---------------------------------------

    def _onStartServer(self):
        """
        Start the OpenIGTLink server on the chosen port via the logic
        class, then start the periodic update timer.
        """
        port = self.portInput.value
        ok = self.logic.startServer(port)
        if not ok:
            slicer.util.errorDisplay(
                f"Could not start server on port {port}.\n"
                f"Check that the port is free."
            )
            return

        self.startBtn.setEnabled(False)
        self.stopBtn.setEnabled(True)
        self.previousServerState = self.logic.getServerState()
        self.updateTimer.start()
        self._updateServerLabels()
        self._refreshVfStatus()

    def _onStopServer(self):
        """
        Stop the server, stop the timer, reset the UI.
        """
        self.logic.stopServer()
        self.startBtn.setEnabled(True)
        self.stopBtn.setEnabled(False)
        self.updateTimer.stop()

        self.serverStatus.setText("Stopped")
        self.serverStatus.setStyleSheet(
            "color: gray; font-weight: bold; font-size: 14px; padding: 5px;"
        )
        self.connectionStatus.setText("No client connected")
        self.connectionStatus.setStyleSheet(
            "color: gray; padding-left: 5px;"
        )

    # -- TIMER TICK -----------------------------------------------

    def _onTimerTick(self):
        """
        Periodic poll: refresh server state labels and the live
        matrix / tip display. Wrapped in try/except so a single
        transient error does not kill the timer.
        """
        try:
            self._updateServerLabels()
            self._updateMatrixDisplay()
            self._updateCollisionLabel()
        except Exception as e:
            import traceback
            print(f"[BiopsyToolOpenIGT] Timer tick error: {e}")
            traceback.print_exc()

    def _updateServerLabels(self):
        """
        Reflect the current connector state in the GUI. Detect
        connect / disconnect edges and update both indicator labels.
        """
        state = self.logic.getServerState()
        port = self.portInput.value

        # Detect connect / disconnect transitions
        if state == 2 and self.previousServerState != 2:
            self.connectionStatus.setText("Client connected")
            self.connectionStatus.setStyleSheet(
                "color: #2a9d3a; font-weight: bold; padding-left: 5px;"
            )
        elif state != 2 and self.previousServerState == 2:
            self.connectionStatus.setText("Client disconnected")
            self.connectionStatus.setStyleSheet(
                "color: orange; padding-left: 5px;"
            )
        self.previousServerState = state

        # Main status text
        if state == 0:
            self.serverStatus.setText("Stopped")
            self.serverStatus.setStyleSheet(
                "color: gray; font-weight: bold; "
                "font-size: 14px; padding: 5px;"
            )
        elif state == 1:
            self.serverStatus.setText(
                f"Waiting for connection (port {port})"
            )
            self.serverStatus.setStyleSheet(
                "color: orange; font-weight: bold; "
                "font-size: 14px; padding: 5px;"
            )
        elif state == 2:
            self.serverStatus.setText(
                f"Active and connected (port {port})"
            )
            self.serverStatus.setStyleSheet(
                "color: #2a9d3a; font-weight: bold; "
                "font-size: 14px; padding: 5px;"
            )

    def _updateMatrixDisplay(self):
        """
        Read the current ToolTipSphere matrix via the logic class
        and, if it changed since the last tick, refresh the matrix
        widget and the tip-position label.
        """
        m = self.logic.getCurrentMatrix()
        if m is None:
            return

        # Cheap change detection by hashing the 16 elements.
        currentHash = hash(tuple(
            m.GetElement(i, j) for i in range(4) for j in range(4)
        ))
        if currentHash == self.lastMatrixHash:
            return
        self.lastMatrixHash = currentHash

        self.messageCounter += 1
        self.msgCountLabel.setText(
            f"Updates received: {self.messageCounter}"
        )

        text = ""
        for i in range(4):
            parts = [f"{m.GetElement(i, j):+8.3f}" for j in range(4)]
            text += "  ".join(parts) + "\n"
        self.matrixDisplay.setText(text)

        # World-space tip position. Because the model's local origin
        # is the tip (pre-calibrated) and the only parent is
        # ToolTipSphere, the tip's world position is the translation
        # column of the parent's matrix-to-world.
        tip = self.logic.getWorldTipPosition()
        if tip is not None:
            self.tipPositionLabel.setText(
                f"RAS = ({tip[0]:+7.2f}, {tip[1]:+7.2f}, "
                f"{tip[2]:+7.2f}) mm"
            )

    def _updateCollisionLabel(self):
        """
        Refresh the Section 4 status label based on the latest value
        held by the logic class. The actual recolouring of the
        VirtualFixture happens inside the logic's observer callback.
        """
        state = self.logic.getLastCollisionState()
        if state == "COLLIDING":
            self.collisionStatus.setText("[!]  COLLISION")
            self.collisionStatus.setStyleSheet(
                "color: white; background-color: #d9534f; "
                "font-weight: bold; font-size: 14px; padding: 10px; "
                "border-radius: 4px;"
            )
        elif state == "FREE":
            self.collisionStatus.setText("[OK]  FREE")
            self.collisionStatus.setStyleSheet(
                "color: white; background-color: #2a9d3a; "
                "font-weight: bold; font-size: 14px; padding: 10px; "
                "border-radius: 4px;"
            )
        # else: leave the "Unknown" placeholder unchanged

    def _refreshVfStatus(self):
        """
        Show whether a VirtualFixture model is present in the scene
        so the user knows whether recolouring will work.
        """
        if self.logic.findVirtualFixtureNode() is not None:
            self.vfStatus.setText("VirtualFixture: detected")
            self.vfStatus.setStyleSheet(
                "color: #2a9d3a; padding-left: 5px;"
            )
        else:
            self.vfStatus.setText(
                "VirtualFixture: not found "
                "(collision state will be tracked but no model "
                "recolouring)"
            )
            self.vfStatus.setStyleSheet(
                "color: orange; padding-left: 5px;"
            )


# ════════════════════════════════════════════════════════════════════
# LOGIC CLASS -- holds all non-UI behaviour
# ════════════════════════════════════════════════════════════════════

class BiopsyToolOpenIGTLogic(ScriptedLoadableModuleLogic):
    """
    Pure logic for the OpenIGT bridge: model loading, server
    start/stop, MRML node lookups, collision observer. No Qt code
    here, so this class can also be driven from a Python console
    script if desired.
    """

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        self.modelNode = None
        self.toolTipSphereNode = None
        self.connectorNode = None
        self.collisionNode = None
        self.collisionObserverTag = None
        # The colour the VirtualFixture had before we first recoloured
        # it. Captured lazily, restored on FREE state and on shutdown.
        self.vfOriginalColor = None
        # Latest received collision state ("COLLIDING" / "FREE" / "").
        self.lastCollisionState = ""

    # -- MODEL HANDLING -------------------------------------------

    def loadAndAttachModel(self, filepath):
        """
        Load a pre-calibrated model file, create a model node from it,
        and attach the result to the ToolTipSphere transform node.
        Removes any previous BiopsyTool / legacy transform nodes so
        repeated loads don't accumulate clutter in the scene.
        """
        # Clean up any previous BiopsyTool-related nodes.
        for nodeName in ("BiopsyTool", "BiopsyToolTransform",
                         "ToolAxisCorrection", "ToolModelScale"):
            n = slicer.mrmlScene.GetFirstNodeByName(nodeName)
            if n:
                slicer.mrmlScene.RemoveNode(n)

        print(f"[BiopsyToolOpenIGT] Loading file: {filepath}")
        polydata = self._readPolydata(filepath)
        print(
            f"[BiopsyToolOpenIGT] Loaded "
            f"{polydata.GetNumberOfPoints()} points, "
            f"{polydata.GetNumberOfCells()} cells"
        )

        # Sanity-check the bounds against the values expected from a
        # file produced by scripts/preprocess_biopsy_tool.py. If the
        # numbers don't match (typically because the user loaded the
        # raw BiopsyTool.stl instead of BiopsyTool_ready.stl) the
        # warning below prints. The model still loads; the user is
        # only nudged to double-check their input.
        #
        # Calibrated reference values:
        #   * long axis ~ 114 mm in Y direction
        #   * disc diameter ~ 61 mm in X and Z
        #   * tip Y near 0 (lower Y endpoint)
        b = polydata.GetBounds()
        xRange = b[1] - b[0]
        yRange = b[3] - b[2]
        zRange = b[5] - b[4]
        print(
            f"[BiopsyToolOpenIGT] Bounds: "
            f"X=[{b[0]:+.2f}, {b[1]:+.2f}] (range {xRange:.1f}), "
            f"Y=[{b[2]:+.2f}, {b[3]:+.2f}] (range {yRange:.1f}), "
            f"Z=[{b[4]:+.2f}, {b[5]:+.2f}] (range {zRange:.1f})"
        )
        looksCalibrated = (
            100 < yRange < 130 and
            xRange < 80 and zRange < 80 and -5 < b[2] < 5
        )
        if not looksCalibrated:
            print(
                "[BiopsyToolOpenIGT] WARNING: bounds don't look like "
                "a calibrated BiopsyTool file (expected long axis "
                "~114mm in Y, tip near Y=0). Did you run "
                "preprocess_biopsy_tool.py?"
            )

        # Create model node from the loaded polydata.
        modelsLogic = slicer.modules.models.logic()
        self.modelNode = modelsLogic.AddModel(polydata)
        self.modelNode.SetName("BiopsyTool")
        print(
            f"[BiopsyToolOpenIGT] Model node created: "
            f"{self.modelNode.GetID()}"
        )

        # Make sure ToolTipSphere exists, then parent the model to it.
        self._ensureToolTipSphere()
        self.modelNode.SetAndObserveTransformNodeID(
            self.toolTipSphereNode.GetID()
        )
        print("[BiopsyToolOpenIGT] Attached to ToolTipSphere")

    def _readPolydata(self, filepath):
        """
        Load a 3D model file directly via VTK, clean it, and return
        an owned (deep-copied) vtkPolyData. Bypassing
        slicer.util.loadModel avoids occasional issues with OBJ
        loaders and gives us a clean, predictable result.
        """
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".stl":
            reader = vtk.vtkSTLReader()
        elif ext == ".obj":
            reader = vtk.vtkOBJReader()
        elif ext == ".ply":
            reader = vtk.vtkPLYReader()
        else:
            raise Exception(
                f"Unsupported file extension '{ext}'. "
                f"Supported: .stl, .obj, .ply"
            )

        reader.SetFileName(filepath)
        reader.Update()

        raw = reader.GetOutput()
        if raw is None or raw.GetNumberOfPoints() == 0:
            raise Exception("Reader produced empty geometry.")

        cleaner = vtk.vtkCleanPolyData()
        cleaner.SetInputData(raw)
        cleaner.Update()

        owned = vtk.vtkPolyData()
        owned.DeepCopy(cleaner.GetOutput())
        return owned

    def _ensureToolTipSphere(self):
        """
        Make sure a vtkMRMLLinearTransformNode named "ToolTipSphere"
        exists. Slicer's OpenIGTLink module automatically routes
        incoming TRANSFORM messages whose device name matches an
        existing node, so creating it explicitly here guarantees the
        first message lands in the node we already have hooked up to
        the BiopsyTool model.
        """
        node = slicer.mrmlScene.GetFirstNodeByName("ToolTipSphere")
        if not node:
            node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLLinearTransformNode", "ToolTipSphere"
            )
        self.toolTipSphereNode = node

    # -- SERVER LIFECYCLE -----------------------------------------

    def startServer(self, port):
        """
        Create / reuse an IGTLConnectorNode in server mode and start
        listening on the given port. Also pre-creates the
        ToolCollision text node and installs the collision observer
        BEFORE any data arrives so the first STRING message is not
        missed.

        Returns True on success, False on failure (e.g. port in use).
        """
        # ToolTipSphere and ToolCollision must exist before Start()
        # so that incoming messages route to nodes we already own.
        self._ensureToolTipSphere()
        self._setupCollisionObserver()

        existing = slicer.mrmlScene.GetFirstNodeByName("IGTLServer")
        if existing:
            # Defensive: if the connector is left over from a previous
            # session (or from a module reload), stop it before
            # reconfiguring so the Start() below sees a clean state.
            try:
                existing.Stop()
            except Exception:
                pass
            self.connectorNode = existing
        else:
            self.connectorNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLIGTLConnectorNode", "IGTLServer"
            )

        self.connectorNode.SetTypeServer(port)
        result = self.connectorNode.Start()
        # OpenIGTLink connector returns 1 on success, 0 on failure
        # (port in use, permission denied, etc.).
        return result == 1

    def stopServer(self):
        """
        Stop the connector node (but keep it in the scene so the user
        can restart without losing configuration). Restore the
        VirtualFixture colour if we changed it.
        """
        if self.connectorNode:
            try:
                self.connectorNode.Stop()
            except Exception:
                pass

        # Best-effort restore of the VirtualFixture colour.
        self._restoreVfColor()

    def getServerState(self):
        """
        Return the current connector state. The values match the
        StateXxx enum exposed by vtkMRMLIGTLConnectorNode:

            0 = StateOff
            1 = StateWaitConnection
            2 = StateConnected

        Polled by the GUI's timer tick to drive the status labels
        in Section 2.
        """
        if self.connectorNode is None:
            return 0
        return self.connectorNode.GetState()

    # -- MATRIX / TIP ACCESS --------------------------------------

    def getCurrentMatrix(self):
        """
        Return the current 4x4 matrix held by ToolTipSphere, or None
        if the node does not exist. Re-fetches by name each call so
        that a node replaced by OpenIGTLink at first contact is
        handled transparently.
        """
        node = slicer.mrmlScene.GetFirstNodeByName("ToolTipSphere")
        if node is None:
            return None
        # Keep the cached reference up to date and re-parent the
        # model if Slicer recreated the node under a new pointer.
        if node != self.toolTipSphereNode:
            self.toolTipSphereNode = node
            if self.modelNode:
                self.modelNode.SetAndObserveTransformNodeID(
                    node.GetID()
                )

        m = vtk.vtkMatrix4x4()
        node.GetMatrixTransformToParent(m)
        return m

    def getWorldTipPosition(self):
        """
        Return the RAS coordinates of the tool tip in world space, or
        None if the model is not yet loaded.
        """
        if self.modelNode is None:
            return None
        parent = self.modelNode.GetParentTransformNode()
        if parent is None:
            return None
        worldMat = vtk.vtkMatrix4x4()
        parent.GetMatrixTransformToWorld(worldMat)
        return [worldMat.GetElement(i, 3) for i in range(3)]

    # -- COLLISION OBSERVER ---------------------------------------

    def _setupCollisionObserver(self):
        """
        Ensure the ToolCollision text node exists and observe it for
        changes. Called BEFORE the server starts so the first STRING
        message has a target node to populate. Otherwise Slicer's
        OpenIGTLink module would create its own node and our observer
        would never see it.
        """
        node = slicer.mrmlScene.GetFirstNodeByName("ToolCollision")
        if not node:
            node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLTextNode", "ToolCollision"
            )
            node.SetText("")

        # Clean up any previous observer before adding a new one.
        self.removeCollisionObserver()

        self.collisionNode = node
        self.collisionObserverTag = node.AddObserver(
            vtk.vtkCommand.ModifiedEvent,
            self._onCollisionStateChanged,
        )
        print(
            "[BiopsyToolOpenIGT] Collision observer "
            "registered on ToolCollision"
        )

    def removeCollisionObserver(self):
        """
        Detach the collision observer if one is currently registered.
        Used by cleanup() and by _setupCollisionObserver() to avoid
        accumulating observers across module reloads.
        """
        if (self.collisionNode is not None
                and self.collisionObserverTag is not None):
            try:
                self.collisionNode.RemoveObserver(
                    self.collisionObserverTag
                )
            except Exception:
                pass
        self.collisionObserverTag = None

    def _onCollisionStateChanged(self, caller, event):
        """
        Observer callback. Stores the latest state and recolours the
        VirtualFixture if present. Intentionally defensive: never
        raises, so a single bad message cannot kill the link.
        """
        try:
            raw = caller.GetText() if caller.GetText() else ""
            state = raw.strip().upper()
            self.lastCollisionState = state

            print(
                f"[BiopsyToolOpenIGT] Collision state received: "
                f"'{state}'"
            )

            # Recolour the VirtualFixture (if present).
            vf = self.findVirtualFixtureNode()
            if vf is None:
                # No VF in the scene -- silently skip the recolour.
                return

            display = vf.GetDisplayNode()
            if display is None:
                return

            # Capture the original colour the first time we touch it.
            if self.vfOriginalColor is None:
                self.vfOriginalColor = display.GetColor()
                print(
                    f"[BiopsyToolOpenIGT] Captured VirtualFixture "
                    f"original colour: {self.vfOriginalColor}"
                )

            if state == "COLLIDING":
                display.SetColor(1.0, 0.1, 0.1)   # red
            else:
                display.SetColor(*self.vfOriginalColor)

        except Exception as e:
            import traceback
            print(
                f"[BiopsyToolOpenIGT] Error in collision observer: "
                f"{e}"
            )
            traceback.print_exc()

    def _restoreVfColor(self):
        """
        Best-effort restore of the VirtualFixture colour to whatever
        we captured the first time we modified it. Called when the
        server stops or the module is unloaded.
        """
        if self.vfOriginalColor is None:
            return
        vf = self.findVirtualFixtureNode()
        if vf is None:
            return
        display = vf.GetDisplayNode()
        if display is None:
            return
        display.SetColor(*self.vfOriginalColor)

    # -- SCENE QUERIES --------------------------------------------

    def findVirtualFixtureNode(self):
        """
        Locate the VirtualFixture model node by name. Returns None if
        no such node exists -- callers must handle this case so the
        module works in scenes that don't have a VF.
        """
        return slicer.mrmlScene.GetFirstNodeByName("VirtualFixture")

    def getLastCollisionState(self):
        """
        Return the last received collision state ("COLLIDING" /
        "FREE" / empty string for unknown).
        """
        return self.lastCollisionState


# ════════════════════════════════════════════════════════════════════
# TEST CLASS -- placeholder, required by Slicer convention
# ════════════════════════════════════════════════════════════════════

class BiopsyToolOpenIGTTest(ScriptedLoadableModuleTest):
    """
    Minimal test placeholder. Real OpenIGTLink integration tests
    require an active server and a connected client, which are not
    feasible to automate without a Unity build in the loop.
    Self-tests for the pure-Python helpers can be added here later.
    """

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.delayDisplay(
            "BiopsyToolOpenIGT has no automated tests yet."
        )
