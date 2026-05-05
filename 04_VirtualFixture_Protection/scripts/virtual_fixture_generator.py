"""
virtual_fixture_generator.py
═══════════════════════════════════════════════════════════════════════════════
Interactive Virtual Fixture (VF) generation in 3D Slicer for biopsy guidance.

GEOMETRY  (from deep to shallow, along the insertion vector):

      ╲        ╱   ← upper cone (frustum), wide funnel for tool ergonomics
       ╲      ╱
        ╲    ╱     ← intermediate cone (frustum), narrow throat that
         ╲  ╱        clears the fiducial screws around the entry
         ││        ← cylinder, runs from skin down to the deep dome
         ││
         ││
        ╭──╮
       ╱    ╲     ← hemisphere, caps the deep end
      ╲______╱

The VF is a closed surface that acts as a forbidden-region constraint:
the biopsy tool tip must remain INSIDE the surface; the surface itself
is the no-fly boundary the controller enforces.

INPUT
    A vtkMRMLMarkupsLineNode with exactly 2 control points:
        • point 0  →  tumour centroid  (deep end)
        • point 1  →  cranium entry    (shallow end)
    Use the "Swap endpoints" toggle in the GUI if your line was drawn
    in the opposite order.

OUTPUT
    A vtkMRMLModelNode named "VirtualFixture" containing a triangle mesh.
    The mesh is rebuilt in real time whenever any parameter or the line
    itself changes.

PARAMETERS  (all live)
    • Diameter             — cylinder ≡ hemisphere diameter, mm
    • Extra past centroid  — distance from centroid to deepest dome point, mm
    • Mid-cone aperture    — full opening angle of the narrow throat, degrees
    • Mid-cone height      — height of the throat (just above the entry), mm
    • Upper-cone aperture  — full opening angle of the wide funnel, degrees
    • Upper-cone height    — height of the wide funnel above the throat, mm

The mid-cone sits directly above P_entry and should stay narrow until it
clears the fiducial screws (~4 mm tall in this project); the upper cone
then flares wide for visualisation and tool clearance above the screws.

USAGE  (Slicer Python Console)
    exec(open(r"/path/to/virtual_fixture_generator.py").read())
"""

import numpy as np
import slicer
import vtk
import qt
import ctk


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — GEOMETRY  (pure VTK, no scene access)
# ═══════════════════════════════════════════════════════════════════════════════

def _rotation_z_to_v(v):
    """
    Return a vtkTransform that rotates the local +Z axis onto the unit
    vector ``v`` (length 3, in world coords). Handles the colinear cases.
    """
    z = np.array([0.0, 0.0, 1.0])
    cross = np.cross(z, v)
    s = float(np.linalg.norm(cross))
    c = float(np.dot(z, v))
    tf = vtk.vtkTransform()
    tf.PostMultiply()
    if s > 1e-9:
        angle_deg = float(np.degrees(np.arctan2(s, c)))
        ax = cross / s
        tf.RotateWXYZ(angle_deg, float(ax[0]), float(ax[1]), float(ax[2]))
    elif c < 0.0:
        # v is anti-parallel to +Z → 180° flip around any orthogonal axis
        tf.RotateWXYZ(180.0, 1.0, 0.0, 0.0)
    # else: v already == +Z, identity rotation
    return tf


def _build_frustum(r_bottom, r_top, height, z_offset, angular_res):
    """
    Build a truncated cone (frustum) by rotating a 1-segment profile around
    +Z. The frustum spans z ∈ [z_offset, z_offset + height] with radius
    ``r_bottom`` at the bottom and ``r_top`` at the top.
    """
    profile_pts = vtk.vtkPoints()
    profile_pts.InsertNextPoint(r_bottom, 0.0, 0.0)
    profile_pts.InsertNextPoint(r_top,    0.0, height)
    profile_lines = vtk.vtkCellArray()
    profile_lines.InsertNextCell(2)
    profile_lines.InsertCellPoint(0)
    profile_lines.InsertCellPoint(1)
    profile_pd = vtk.vtkPolyData()
    profile_pd.SetPoints(profile_pts)
    profile_pd.SetLines(profile_lines)

    rev = vtk.vtkRotationalExtrusionFilter()
    rev.SetInputData(profile_pd)
    rev.SetResolution(angular_res)
    rev.SetAngle(360.0)
    rev.SetCapping(0)
    rev.Update()

    if abs(z_offset) > 1e-12:
        tf = vtk.vtkTransform()
        tf.PostMultiply()
        tf.Translate(0.0, 0.0, float(z_offset))
        flt = vtk.vtkTransformPolyDataFilter()
        flt.SetTransform(tf)
        flt.SetInputConnection(rev.GetOutputPort())
        flt.Update()
        return flt.GetOutput()
    return rev.GetOutput()


def build_vf_polydata(p_centroid, p_entry,
                      diameter, mm_extra,
                      mid_cone_aperture_deg, mid_cone_height,
                      upper_cone_aperture_deg, upper_cone_height,
                      angular_res=64,
                      min_cyl_len=1e-3):
    """
    Build the VF triangle mesh in world (RAS) coordinates.

    Parameters
    ----------
    p_centroid, p_entry : array-like (3,)
        Endpoints of the insertion line in RAS millimetres.
    diameter : float
        Diameter of cylinder = diameter of hemisphere, mm.
    mm_extra : float
        Distance from ``p_centroid`` to the deepest tip of the hemisphere, mm.
    mid_cone_aperture_deg : float
        Full opening angle of the intermediate (narrow) cone, degrees.
    mid_cone_height : float
        Height of the intermediate cone above ``p_entry``, mm. Should be tall
        enough to clear any obstacles around the entry (e.g. 4 mm screws).
    upper_cone_aperture_deg : float
        Full opening angle of the upper (wide) cone, degrees.
    upper_cone_height : float
        Height of the upper cone above the intermediate cone, mm.
    angular_res : int
        Circumferential subdivision of all primitives.
    min_cyl_len : float
        Minimum acceptable cylinder length, mm. Below this an exception is
        raised so the GUI can show a sensible warning.

    Returns
    -------
    vtk.vtkPolyData
        A closed triangle mesh in RAS coordinates with smooth normals.
    """
    p_centroid = np.asarray(p_centroid, dtype=float)
    p_entry    = np.asarray(p_entry,    dtype=float)

    radius = float(diameter) / 2.0

    # Insertion axis: unit vector from deep (centroid) to shallow (entry)
    axis_vec = p_entry - p_centroid
    L_axis   = float(np.linalg.norm(axis_vec))
    if L_axis < 1e-6:
        raise ValueError("Insertion vector has zero length.")
    v = axis_vec / L_axis

    # ── Length of cylinder along the axis ──────────────────────────────────
    # Local frame, +Z = v, origin at hemisphere centre (= cylinder base):
    #   hemisphere   : z ∈ [-radius              , 0                                  ]
    #   cylinder     : z ∈ [    0                , cyl_len                             ]
    #   intermediate : z ∈ [cyl_len              , cyl_len + h_mid                     ]
    #   upper cone   : z ∈ [cyl_len + h_mid      , cyl_len + h_mid + h_top             ]
    # The cylinder top must coincide with p_entry, so
    #   cyl_len = (p_entry − dome_centre) · v = L_axis − radius + mm_extra
    cyl_len = L_axis - radius + mm_extra
    if cyl_len < min_cyl_len:
        raise ValueError(
            f"Cylinder length is {cyl_len:.2f} mm. "
            f"Increase the 'extra past centroid' margin or check the line.")

    # ── Frustum radii: each cone starts where the previous one ended ───────
    half_mid = np.radians(mid_cone_aperture_deg   / 2.0)
    half_top = np.radians(upper_cone_aperture_deg / 2.0)
    r_mid    = radius + mid_cone_height   * np.tan(half_mid)   # throat top
    r_top    = r_mid  + upper_cone_height * np.tan(half_top)   # funnel top

    appender = vtk.vtkAppendPolyData()

    # ── 1. Hemisphere ──────────────────────────────────────────────────────
    sphere = vtk.vtkSphereSource()
    sphere.SetCenter(0.0, 0.0, 0.0)
    sphere.SetRadius(radius)
    sphere.SetThetaResolution(angular_res)
    sphere.SetPhiResolution(angular_res)
    sphere.SetStartPhi(90)        # equator (z = 0)
    sphere.SetEndPhi(180)         # south pole (z = −radius)
    sphere.LatLongTessellationOn()
    sphere.Update()
    appender.AddInputData(sphere.GetOutput())

    # ── 2. Cylinder ────────────────────────────────────────────────────────
    cyl = vtk.vtkCylinderSource()
    cyl.SetRadius(radius)
    cyl.SetHeight(cyl_len)
    cyl.SetResolution(angular_res)
    cyl.SetCapping(False)         # hemisphere caps the bottom; mid-cone joins top
    # vtkCylinderSource is Y-aligned and centred at the origin (spans Y in
    # [-h/2, +h/2]). In PostMultiply mode the operations are applied in the
    # order written to each vertex p:
    #   1. Translate(0, h/2, 0)  → cylinder spans Y in [0, cyl_len]
    #   2. RotateX(+90)          → +Y → +Z, so it spans Z in [0, cyl_len]
    cyl_tf = vtk.vtkTransform()
    cyl_tf.PostMultiply()
    cyl_tf.Translate(0.0, cyl_len / 2.0, 0.0)
    cyl_tf.RotateX(90.0)
    cyl_filt = vtk.vtkTransformPolyDataFilter()
    cyl_filt.SetTransform(cyl_tf)
    cyl_filt.SetInputConnection(cyl.GetOutputPort())
    cyl_filt.Update()
    appender.AddInputData(cyl_filt.GetOutput())

    # ── 3. Intermediate cone (narrow throat, just above the entry) ─────────
    if mid_cone_height > 0.0:
        appender.AddInputData(_build_frustum(
            r_bottom=radius, r_top=r_mid,
            height=mid_cone_height, z_offset=cyl_len,
            angular_res=angular_res))

    # ── 4. Upper cone (wide funnel, above the throat) ──────────────────────
    if upper_cone_height > 0.0:
        appender.AddInputData(_build_frustum(
            r_bottom=r_mid, r_top=r_top,
            height=upper_cone_height, z_offset=cyl_len + mid_cone_height,
            angular_res=angular_res))

    appender.Update()

    # ── World transform: align local +Z to v, then place dome centre ───────
    # Dome centre in world = p_centroid + (radius − mm_extra)·v
    p_dome_center = p_centroid + (radius - mm_extra) * v

    world_tf = _rotation_z_to_v(v)
    world_tf.Translate(float(p_dome_center[0]),
                       float(p_dome_center[1]),
                       float(p_dome_center[2]))

    world_filt = vtk.vtkTransformPolyDataFilter()
    world_filt.SetTransform(world_tf)
    world_filt.SetInputConnection(appender.GetOutputPort())
    world_filt.Update()

    # ── Triangulate (some sources emit quads) and compute smooth normals ───
    tri = vtk.vtkTriangleFilter()
    tri.SetInputConnection(world_filt.GetOutputPort())
    tri.Update()

    normals = vtk.vtkPolyDataNormals()
    normals.SetInputConnection(tri.GetOutputPort())
    normals.ConsistencyOn()
    normals.SplittingOff()
    normals.Update()

    out = vtk.vtkPolyData()
    out.DeepCopy(normals.GetOutput())
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — SCENE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

VF_MODEL_NAME = "VirtualFixture"


def _find_model_by_name(name):
    """Return an existing vtkMRMLModelNode with this name, or None."""
    for n in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        if n.GetName() == name:
            return n
    return None


def _get_or_create_vf_model(color=(0.20, 1.00, 0.40), opacity=0.35):
    """Get the VF model node, creating it (with display node) if needed."""
    node = _find_model_by_name(VF_MODEL_NAME)
    if node is None:
        node = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode", VF_MODEL_NAME)
        node.CreateDefaultDisplayNodes()
    dn = node.GetDisplayNode()
    if dn is None:
        node.CreateDefaultDisplayNodes()
        dn = node.GetDisplayNode()
    dn.SetColor(*color)
    dn.SetOpacity(opacity)
    dn.SetVisibility2D(True)
    dn.SetSliceIntersectionThickness(2)
    dn.SetBackfaceCulling(False)
    return node


def _line_endpoints_ras(line_node, swap=False):
    """
    Return (centroid, entry) as numpy arrays of shape (3,) in RAS,
    or (None, None) if the line is missing/incomplete.
    """
    if line_node is None or line_node.GetNumberOfControlPoints() < 2:
        return None, None
    p0 = [0.0, 0.0, 0.0]
    p1 = [0.0, 0.0, 0.0]
    line_node.GetNthControlPointPositionWorld(0, p0)
    line_node.GetNthControlPointPositionWorld(1, p1)
    p0 = np.array(p0); p1 = np.array(p1)
    return (p1, p0) if swap else (p0, p1)


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class VirtualFixtureDialog(qt.QDialog):
    """Floating dialog that creates and continuously updates the VF model."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Virtual Fixture Generator")
        self.setMinimumWidth(420)

        self._modelNode      = None
        self._observedLine   = None
        self._lineObsTag     = None

        self._build_ui()
        self._populate_lines()

    # ─────────────────────────────────────────────────────────────────────
    #  UI construction
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = qt.QVBoxLayout(self)
        outer.setSpacing(8)

        # Header --------------------------------------------------------------
        hdr = qt.QLabel(
            "<h3 style='margin:0; color:#2e86c1;'>Virtual Fixture Generator</h3>"
            "<span style='color:#888; font-size:10px;'>"
            "Hemisphere → cylinder → throat → funnel · forbidden-region VF</span>")
        outer.addWidget(hdr)

        # Step 1 — insertion line --------------------------------------------
        g1 = qt.QGroupBox("1 · Insertion vector  (markups line node)")
        l1 = qt.QVBoxLayout(g1)

        rowA = qt.QHBoxLayout()
        rowA.addWidget(qt.QLabel("Line node:"))
        self.lineCombo = qt.QComboBox()
        self.lineCombo.setMinimumWidth(200)
        rowA.addWidget(self.lineCombo, 1)
        self.refreshBtn = qt.QPushButton("⟳")
        self.refreshBtn.setToolTip("Refresh the list of markups lines")
        self.refreshBtn.setFixedWidth(32)
        rowA.addWidget(self.refreshBtn)
        l1.addLayout(rowA)

        self.swapChk = qt.QCheckBox(
            "Swap endpoints  (tick if P0 = entry, P1 = centroid)")
        l1.addWidget(self.swapChk)

        self.endpointsLabel = qt.QLabel("—")
        self.endpointsLabel.setStyleSheet(
            "font-family:monospace; font-size:10px; color:#0e0; "
            "background:#101010; padding:4px; border-radius:3px;")
        self.endpointsLabel.setWordWrap(True)
        l1.addWidget(self.endpointsLabel)

        outer.addWidget(g1)

        # Step 2 — parameters -------------------------------------------------
        g2 = qt.QGroupBox("2 · Geometry parameters  (live update)")
        l2 = qt.QFormLayout(g2)
        l2.setLabelAlignment(qt.Qt.AlignRight)

        self.diaWidget = self._make_slider(
            vmin=1.0, vmax=30.0, vinit=6.0, step=0.1, decimals=2, suffix=" mm")
        l2.addRow("Diameter (cyl ≡ hemisphere)", self.diaWidget)

        self.extraWidget = self._make_slider(
            vmin=0.0, vmax=30.0, vinit=5.0, step=0.1, decimals=2, suffix=" mm")
        l2.addRow("Extra past centroid", self.extraWidget)

        # Intermediate ("throat") cone — narrow, clears the fiducial screws
        self.midApWidget = self._make_slider(
            vmin=0.0, vmax=90.0, vinit=10.0, step=0.5, decimals=1, suffix=" °")
        l2.addRow("Mid-cone aperture (narrow)", self.midApWidget)

        self.midHWidget = self._make_slider(
            vmin=0.0, vmax=60.0, vinit=10.0, step=0.5, decimals=1, suffix=" mm")
        l2.addRow("Mid-cone height (above entry)", self.midHWidget)

        # Upper ("funnel") cone — wide, for tool ergonomics above the screws
        self.topApWidget = self._make_slider(
            vmin=0.0, vmax=150.0, vinit=60.0, step=1.0, decimals=1, suffix=" °")
        l2.addRow("Upper-cone aperture (wide)", self.topApWidget)

        self.topHWidget = self._make_slider(
            vmin=0.0, vmax=100.0, vinit=25.0, step=0.5, decimals=1, suffix=" mm")
        l2.addRow("Upper-cone height (above mid)", self.topHWidget)

        outer.addWidget(g2)

        # Step 3 — display & actions -----------------------------------------
        g3 = qt.QGroupBox("3 · Display & actions")
        l3 = qt.QVBoxLayout(g3)

        rowO = qt.QHBoxLayout()
        rowO.addWidget(qt.QLabel("Opacity:"))
        self.opacitySpin = qt.QDoubleSpinBox()
        self.opacitySpin.setRange(0.05, 1.0)
        self.opacitySpin.setSingleStep(0.05)
        self.opacitySpin.setDecimals(2)
        self.opacitySpin.setValue(0.35)
        rowO.addWidget(self.opacitySpin)
        rowO.addSpacing(20)
        self.colorBtn = qt.QPushButton("Pick colour…")
        rowO.addWidget(self.colorBtn)
        rowO.addStretch()
        l3.addLayout(rowO)

        rowB = qt.QHBoxLayout()
        self.exportSTLBtn = qt.QPushButton("💾  Export as STL")
        self.exportSTLBtn.setToolTip("Save the current mesh to an .stl file.")
        rowB.addWidget(self.exportSTLBtn)
        self.deleteBtn = qt.QPushButton("🗑  Delete VF")
        self.deleteBtn.setStyleSheet("color:#e74c3c;")
        rowB.addWidget(self.deleteBtn)
        l3.addLayout(rowB)

        self.statusLabel = qt.QLabel("")
        self.statusLabel.setStyleSheet("color:#bbb; font-size:10px; padding:2px;")
        self.statusLabel.setWordWrap(True)
        l3.addWidget(self.statusLabel)

        outer.addWidget(g3)

        # Connections --------------------------------------------------------
        self.refreshBtn.clicked.connect(self._populate_lines)
        self.lineCombo.currentIndexChanged.connect(self._on_line_changed)
        self.swapChk.toggled.connect(self._update_vf)
        self.opacitySpin.valueChanged.connect(self._on_opacity_changed)
        self.colorBtn.clicked.connect(self._on_pick_color)
        self.exportSTLBtn.clicked.connect(self._on_export_stl)
        self.deleteBtn.clicked.connect(self._on_delete)
        for w in (self.diaWidget, self.extraWidget,
                  self.midApWidget, self.midHWidget,
                  self.topApWidget, self.topHWidget):
            w.valueChanged.connect(self._update_vf)

    def _make_slider(self, vmin, vmax, vinit, step, decimals, suffix):
        """Return a ctkSliderWidget configured with the given range."""
        w = ctk.ctkSliderWidget()
        w.minimum = float(vmin)
        w.maximum = float(vmax)
        w.singleStep = float(step)
        w.decimals = int(decimals)
        w.suffix = suffix
        w.value = float(vinit)
        return w

    # ─────────────────────────────────────────────────────────────────────
    #  Line node management
    # ─────────────────────────────────────────────────────────────────────

    def _populate_lines(self):
        self.lineCombo.blockSignals(True)
        prev = self.lineCombo.currentText
        self.lineCombo.clear()
        self.lineCombo.addItem("— select a line —")
        for n in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode"):
            self.lineCombo.addItem(n.GetName())
        # Restore previous selection if still present
        idx = self.lineCombo.findText(prev) if prev else -1
        if idx < 0 and self.lineCombo.count > 1:
            idx = 1   # auto-pick the first real entry
        if idx > 0:
            self.lineCombo.setCurrentIndex(idx)
        self.lineCombo.blockSignals(False)
        self._on_line_changed(self.lineCombo.currentIndex)

    def _current_line_node(self):
        name = self.lineCombo.currentText
        if not name or name.startswith("—"):
            return None
        try:
            return slicer.util.getNode(name)
        except Exception:
            return None

    def _attach_line_observer(self, node):
        # Detach previous
        if self._observedLine is not None and self._lineObsTag is not None:
            try:
                self._observedLine.RemoveObserver(self._lineObsTag)
            except Exception:
                pass
        self._observedLine = None
        self._lineObsTag   = None

        if node is None:
            return
        self._observedLine = node
        # Update on any control-point modification or addition
        ev = slicer.vtkMRMLMarkupsNode.PointModifiedEvent
        self._lineObsTag = node.AddObserver(ev, lambda *a: self._update_vf())

    def _on_line_changed(self, _idx):
        self._attach_line_observer(self._current_line_node())
        self._update_vf()

    # ─────────────────────────────────────────────────────────────────────
    #  Main update — rebuild the mesh from the current parameters
    # ─────────────────────────────────────────────────────────────────────

    def _update_vf(self, *_):
        line = self._current_line_node()
        p_c, p_e = _line_endpoints_ras(line, swap=self.swapChk.isChecked())

        if p_c is None or p_e is None:
            self.endpointsLabel.setText(
                "Select a markups line with 2 control points.")
            self.statusLabel.setText("")
            return

        L = float(np.linalg.norm(p_e - p_c))
        self.endpointsLabel.setText(
            f"P_centroid = ({p_c[0]:+8.2f}, {p_c[1]:+8.2f}, {p_c[2]:+8.2f}) mm\n"
            f"P_entry    = ({p_e[0]:+8.2f}, {p_e[1]:+8.2f}, {p_e[2]:+8.2f}) mm\n"
            f"|axis|     = {L:.2f} mm")

        try:
            poly = build_vf_polydata(
                p_c, p_e,
                diameter                = float(self.diaWidget.value),
                mm_extra                = float(self.extraWidget.value),
                mid_cone_aperture_deg   = float(self.midApWidget.value),
                mid_cone_height         = float(self.midHWidget.value),
                upper_cone_aperture_deg = float(self.topApWidget.value),
                upper_cone_height       = float(self.topHWidget.value),
            )
        except Exception as e:
            self.statusLabel.setText(f"⚠  {e}")
            self.statusLabel.setStyleSheet(
                "color:#e74c3c; font-size:10px; padding:2px;")
            return

        if self._modelNode is None:
            self._modelNode = _get_or_create_vf_model(
                color=(0.20, 1.00, 0.40),
                opacity=float(self.opacitySpin.value))
        self._modelNode.SetAndObserveMesh(poly)

        n_tri = poly.GetNumberOfCells()
        n_pts = poly.GetNumberOfPoints()
        self.statusLabel.setText(
            f"✓  VF mesh updated · {n_tri} triangles · {n_pts} vertices")
        self.statusLabel.setStyleSheet(
            "color:#2ecc71; font-size:10px; padding:2px;")

    # ─────────────────────────────────────────────────────────────────────
    #  Display / file callbacks
    # ─────────────────────────────────────────────────────────────────────

    def _on_opacity_changed(self, v):
        if self._modelNode and self._modelNode.GetDisplayNode():
            self._modelNode.GetDisplayNode().SetOpacity(float(v))

    def _on_pick_color(self):
        if self._modelNode is None or self._modelNode.GetDisplayNode() is None:
            return
        dn = self._modelNode.GetDisplayNode()
        cur = dn.GetColor()
        qcol = qt.QColorDialog.getColor(
            qt.QColor.fromRgbF(*cur), self, "Choose VF colour")
        if qcol.isValid():
            dn.SetColor(qcol.redF(), qcol.greenF(), qcol.blueF())

    def _on_export_stl(self):
        if self._modelNode is None:
            slicer.util.warningDisplay("No VF mesh to export yet.")
            return
        result = qt.QFileDialog.getSaveFileName(
            self, "Export Virtual Fixture as STL",
            "VirtualFixture.stl", "STL files (*.stl)")
        path = result[0] if isinstance(result, tuple) else result
        if not path:
            return
        ok = slicer.util.saveNode(self._modelNode, path)
        if ok:
            self.statusLabel.setText(f"✓  Saved → {path}")
        else:
            self.statusLabel.setText(f"⚠  Failed to save {path}")

    def _on_delete(self):
        if self._modelNode is not None:
            slicer.mrmlScene.RemoveNode(self._modelNode)
            self._modelNode = None
            self.statusLabel.setText("VF removed from the scene.")

    # ─────────────────────────────────────────────────────────────────────
    #  Cleanup
    # ─────────────────────────────────────────────────────────────────────

    def closeEvent(self, ev):
        # Detach the observer; leave the model node in the scene.
        self._attach_line_observer(None)
        super().closeEvent(ev)


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

# Close any leftover dialog from a previous exec() of this script
try:
    _vf_dlg.close()         # noqa: F821
    _vf_dlg.deleteLater()   # noqa: F821
except Exception:
    pass

_vf_dlg = VirtualFixtureDialog(slicer.util.mainWindow())
_vf_dlg.setAttribute(qt.Qt.WA_DeleteOnClose, False)
_vf_dlg.show()
_vf_dlg.raise_()

print("✓ Virtual Fixture Generator opened.")
