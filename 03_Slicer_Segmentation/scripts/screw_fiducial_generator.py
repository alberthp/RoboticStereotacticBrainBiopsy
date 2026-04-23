"""
screw_fiducial_generator.py
═══════════════════════════
Automated fiducial marker placement on segmented bone screws in 3D Slicer.

Workflow:
    1. User segments all screws into a single Slicer segment
    2. Script splits them via connected component analysis (scipy.ndimage.label)
    3. PCA on each component's voxel cloud → long axis → tip detection
    4. Tip = endpoint farthest from the global centroid of all screws
    5. GUI allows fine-tuning of each tip position after computation

Output nodes created in the Slicer scene:
    - ScrewTips       (orange)  : fiducial markers at each screw tip
    - ScrewCentroids  (cyan)    : centroid of each screw (locked reference)
    - ScrewAxes/                : Subject Hierarchy folder of axis lines

Requirements: 3D Slicer 5.x, numpy, scipy (both included in Slicer Python)

Usage (Slicer Python Console):
    exec(open(r"path/to/screw_fiducial_generator.py").read())
"""

import numpy as np
import slicer
import vtk
from scipy import ndimage
import qt


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — GEOMETRY & SLICER HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_labelmap_and_matrix(segNode, segId):
    """
    Export a single segment from a segmentation node into a temporary
    labelmap volume and return the voxel array plus the IJK→RAS transform.

    Parameters
    ----------
    segNode : vtkMRMLSegmentationNode
        The Slicer segmentation node containing the segment.
    segId : str
        The segment ID string (not the display name).

    Returns
    -------
    arr : ndarray, shape (k, j, i)
        3-D numpy array; foreground voxels have value > 0.
    ijkToRas : vtkMatrix4x4
        4×4 affine matrix mapping IJK voxel indices to RAS mm coordinates.
    labelmapNode : vtkMRMLLabelMapVolumeNode
        Temporary node — caller is responsible for removing it when done.
    """
    labelmapNode = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLLabelMapVolumeNode", "__tmp__")
    slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(
        segNode, [segId], labelmapNode, None)
    arr = slicer.util.arrayFromVolume(labelmapNode)   # (k, j, i) order
    ijkToRas = vtk.vtkMatrix4x4()
    labelmapNode.GetIJKToRASMatrix(ijkToRas)
    return arr, ijkToRas, labelmapNode


def voxels_to_ras(ijk_indices, matrix):
    """
    Convert an array of IJK voxel indices to RAS millimetre coordinates.

    Parameters
    ----------
    ijk_indices : ndarray, shape (N, 3)
        Each row is (k, j, i) — note the numpy axis order from argwhere.
    matrix : vtkMatrix4x4
        The IJK→RAS affine matrix from the labelmap volume.

    Returns
    -------
    ndarray, shape (N, 3)
        Each row is (R, A, S) in mm.
    """
    result = []
    for k, j, i in ijk_indices:
        # Build homogeneous coordinate; vtkMatrix uses (i, j, k) column order
        h   = [i, j, k, 1]
        ras = [sum(matrix.GetElement(r, c) * h[c]
                   for c in range(4)) for r in range(3)]
        result.append(ras)
    return np.array(result)


def pca_long_axis(coords):
    """
    Find the principal (long) axis of a point cloud using PCA.

    The covariance matrix of the centred coordinates is decomposed; the
    eigenvector with the largest eigenvalue points along the direction of
    maximum variance, which corresponds to the screw shaft.

    Parameters
    ----------
    coords : ndarray, shape (N, 3)
        RAS coordinates of all voxels in one screw component.

    Returns
    -------
    long_axis : ndarray, shape (3,)
        Unit vector pointing along the screw's long axis.
    vals : ndarray, shape (3,)
        Eigenvalues (ascending); useful for checking elongation quality.
    """
    centered = coords - coords.mean(axis=0)
    vals, vecs = np.linalg.eigh(np.cov(centered.T))   # ascending order
    long_axis  = vecs[:, np.argmax(vals)]              # largest eigenvalue
    return long_axis, vals


def find_tip_and_base(coords, centroid, long_axis, global_centroid):
    """
    Determine which end of the screw long axis is the tip (exposed head)
    and which is the base (anchored in bone).

    Strategy: project all voxels onto the long axis to find both extreme
    endpoints, then pick the endpoint that is FARTHEST from the global
    centroid of all screws combined. The screw head protrudes outward
    from the bone mass, so it is always the more distant end.

    Parameters
    ----------
    coords : ndarray, shape (N, 3)
        RAS coordinates of this screw's voxels.
    centroid : ndarray, shape (3,)
        Mean RAS position of this screw.
    long_axis : ndarray, shape (3,)
        Unit long-axis vector from pca_long_axis().
    global_centroid : ndarray, shape (3,)
        Mean RAS position of ALL screw voxels combined.

    Returns
    -------
    tip : ndarray, shape (3,)
        RAS position of the screw tip (exposed head).
    base : ndarray, shape (3,)
        RAS position of the screw base (bone-anchored end).
    """
    # Scalar projection of each voxel onto the long axis
    proj = (coords - centroid) @ long_axis
    end1 = coords[np.argmax(proj)]   # one extreme
    end2 = coords[np.argmin(proj)]   # opposite extreme

    # The tip is the end farther from the overall bone centroid
    d1 = np.linalg.norm(end1 - global_centroid)
    d2 = np.linalg.norm(end2 - global_centroid)
    return (end1, end2) if d1 >= d2 else (end2, end1)


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — SLICER NODE FACTORIES
# ═══════════════════════════════════════════════════════════════════════════════

def make_fiducial_node(name, color_rgb):
    """
    Create a new MarkupsFiducialNode in the scene with the given colour.

    Parameters
    ----------
    name : str
        Node name as it will appear in the Data module.
    color_rgb : tuple of float
        (R, G, B) each in [0, 1].

    Returns
    -------
    vtkMRMLMarkupsFiducialNode
    """
    node = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLMarkupsFiducialNode", name)
    dn = node.GetDisplayNode()
    dn.SetSelectedColor(*color_rgb)
    dn.SetColor(*color_rgb)
    dn.SetGlyphScale(2.0)
    dn.SetTextScale(3.0)
    return node


def make_line_node(name, color_rgb):
    """
    Create a new MarkupsLineNode in the scene with the given colour.
    Used to visualise the centroid→tip axis of each screw.
    """
    node = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLMarkupsLineNode", name)
    dn = node.GetDisplayNode()
    dn.SetSelectedColor(*color_rgb)
    dn.SetColor(*color_rgb)
    return node


def group_nodes_in_folder(folder_name, node_list):
    """
    Create a Subject Hierarchy folder and move a list of nodes into it.
    This keeps the Data module tidy when many axis lines are created.

    Parameters
    ----------
    folder_name : str
        Display name for the new folder.
    node_list : list of vtkMRMLNode
        Nodes to move into the folder.

    Returns
    -------
    int
        Subject Hierarchy item ID of the new folder.
    """
    shNode   = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(
        slicer.mrmlScene)
    sceneId  = shNode.GetSceneItemID()
    folderId = shNode.CreateFolderItem(sceneId, folder_name)
    for node in node_list:
        itemId = shNode.GetItemByDataNode(node)
        shNode.SetItemParent(itemId, folderId)
    return folderId


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — ARTIFACT THRESHOLD
# ═══════════════════════════════════════════════════════════════════════════════

def compute_auto_threshold(sizes, pct_of_median):
    """
    Compute an automatic artifact size threshold.

    The threshold is a percentage of the median component size, so it
    adapts to the actual screw sizes in the scan rather than requiring
    the user to guess an absolute voxel count.

    Parameters
    ----------
    sizes : list of int
        Voxel count of each connected component.
    pct_of_median : float
        Percentage of the median to use as the threshold (e.g. 20 → 20%).

    Returns
    -------
    threshold : float
        Absolute voxel count below which a component is an artifact.
    median : float
        Median voxel count (shown in the GUI for reference).
    """
    median = float(np.median(sizes))
    return median * (pct_of_median / 100.0), median


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — MAIN PROCESSING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def identify_screws(seg_node_name, seg_segment_name):
    """
    Export the named segment to a labelmap and run connected component
    analysis to identify each isolated screw volume.

    This is intentionally separate from run_pipeline() so the GUI can
    show the component list and let the user inspect/clean artifacts
    before committing to the full computation.

    Parameters
    ----------
    seg_node_name : str
        Name of the vtkMRMLSegmentationNode in the scene.
    seg_segment_name : str
        Display name of the segment within that node.

    Returns
    -------
    labeled : ndarray
        Integer array; voxels of component i have value i (1-based).
    ijkToRas : vtkMatrix4x4
        IJK→RAS transform of the exported labelmap.
    n : int
        Number of connected components found.
    sizes : list of int
        Voxel count of each component (index 0 = component 1).
    labelmapNode : vtkMRMLLabelMapVolumeNode
        Temporary node — caller removes it after run_pipeline().
    """
    segNode = slicer.util.getNode(seg_node_name)
    seg     = segNode.GetSegmentation()
    segId   = seg.GetSegmentIdBySegmentName(seg_segment_name)

    arr, ijkToRas, labelmapNode = get_labelmap_and_matrix(segNode, segId)

    # Label each isolated foreground blob with a unique integer
    labeled, n = ndimage.label(arr > 0)
    sizes = [int((labeled == i).sum()) for i in range(1, n + 1)]

    return labeled, ijkToRas, n, sizes, labelmapNode


def run_pipeline(labeled, ijkToRas, n, sizes, abs_threshold, labelmapNode):
    """
    Process each valid connected component (screw) and create markup nodes.

    Components with voxel count ≤ abs_threshold are skipped as artifacts.
    For each valid component:
        1. Convert voxels to RAS coordinates
        2. Compute centroid (mean position)
        3. PCA → long axis direction
        4. Find tip (farthest endpoint from global centroid)
        5. Create control points in ScrewTips and ScrewCentroids nodes
        6. Create centroid→tip axis line

    Parameters
    ----------
    labeled : ndarray
        Output of identify_screws() — integer component labels.
    ijkToRas : vtkMatrix4x4
        IJK→RAS transform.
    n : int
        Total number of components (including artifacts).
    sizes : list of int
        Voxel count per component.
    abs_threshold : float
        Components with size ≤ this value are skipped.
    labelmapNode : vtkMRMLLabelMapVolumeNode
        Temporary node — removed at the end of this function.

    Returns
    -------
    results : list of dict
        One dict per valid screw with keys:
        'name', 'centroid', 'tip', 'variance'
    tipsNode : vtkMRMLMarkupsFiducialNode
        The ScrewTips node (interactive, returned for Step 4 fine-tuning).
    """
    print(f"\n▶ Computing fiducials (skipping ≤ {abs_threshold:.0f} voxels)...")

    # Global centroid used for tip/base disambiguation across all screws
    all_coords      = voxels_to_ras(np.argwhere(labeled > 0), ijkToRas)
    global_centroid = all_coords.mean(axis=0)

    # Create output markup nodes
    tipsNode      = make_fiducial_node("ScrewTips",      (1.0, 0.4, 0.0))
    centroidsNode = make_fiducial_node("ScrewCentroids", (0.0, 0.8, 1.0))

    # Tips are interactive — user can drag them for fine-tuning
    tipsNode.SetLocked(False)
    tipsNode.GetDisplayNode().SetSnapMode(
        slicer.vtkMRMLMarkupsDisplayNode.SnapModeToVisibleSurface)

    axis_nodes = []   # collected for Subject Hierarchy grouping
    results    = []
    skipped    = 0

    for comp_id in range(1, n + 1):
        sz = sizes[comp_id - 1]

        # Skip artifact components below the size threshold
        if sz <= abs_threshold:
            skipped += 1
            print(f"  [Vol {comp_id:02d}]  SKIPPED ({sz} vx)")
            continue

        # ── Extract voxel cloud for this screw ────────────────────────────
        ijk_idx  = np.argwhere(labeled == comp_id)
        coords   = voxels_to_ras(ijk_idx, ijkToRas)

        # ── Geometric computation ─────────────────────────────────────────
        centroid          = coords.mean(axis=0)
        long_axis, eigenvalues = pca_long_axis(coords)
        variance          = eigenvalues / eigenvalues.sum() * 100  # % per axis
        tip, base         = find_tip_and_base(
            coords, centroid, long_axis, global_centroid)

        # ── Store result ──────────────────────────────────────────────────
        name = f"Screw_{len(results)+1:02d}"
        results.append({"name": name, "centroid": centroid,
                        "tip": tip, "variance": variance})

        # ── ScrewTips — one draggable point per screw ─────────────────────
        idx = tipsNode.AddControlPoint(tip.tolist())
        tipsNode.SetNthControlPointLabel(idx, name)
        tipsNode.SetNthControlPointLocked(idx, False)   # remains interactive

        # ── ScrewCentroids — locked reference point ───────────────────────
        idx = centroidsNode.AddControlPoint(centroid.tolist())
        centroidsNode.SetNthControlPointLabel(idx, f"Ctr_{name}")
        centroidsNode.SetNthControlPointLocked(idx, True)

        # ── Axis line: centroid → tip ─────────────────────────────────────
        lineNode = make_line_node(f"Axis_{name}", (1.0, 1.0, 0.0))
        lineNode.AddControlPoint(centroid.tolist())
        lineNode.AddControlPoint(tip.tolist())
        lineNode.SetLocked(True)                        # display only
        axis_nodes.append(lineNode)

        # PCA quality check: if long-axis variance >> 33%, screw is elongated
        quality = "✓" if variance[2] > 50 else "⚠ check shape"
        print(f"  [{name}]  voxels={sz:5d}  "
              f"PCA={np.round(variance[2],1):5.1f}%  {quality}")

    # Group all axis lines in a Subject Hierarchy folder
    group_nodes_in_folder("ScrewAxes", axis_nodes)

    # Remove the temporary labelmap — no longer needed
    slicer.mrmlScene.RemoveNode(labelmapNode)

    print(f"\n✓ {len(results)} screws processed, {skipped} artifact(s) skipped.")
    return results, tipsNode


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# RAS axis definitions for the fine-tune buttons in Step 4
# Each tuple: (display label, RAS index 0=R/1=A/2=S, button colour hex)
AXES = [
    ("R  (Right)",     0, "#e74c3c"),   # red
    ("A  (Anterior)",  1, "#2ecc71"),   # green
    ("S  (Superior)",  2, "#3498db"),   # blue
]

# Default percentage of median used as the artifact threshold at startup
DEFAULT_PCT = 20


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — COLLAPSIBLE SECTION WIDGET
# ═══════════════════════════════════════════════════════════════════════════════

class CollapsibleSection(qt.QWidget):
    """
    A titled panel whose content can be shown/hidden by clicking the header.

    Used to keep the dialog compact: Steps 1-3 are expanded by default;
    Step 4 starts collapsed and is unlocked only after Step 3 completes.

    Usage:
        sec = CollapsibleSection("My Section")
        sec.addWidget(some_widget)
        layout.addWidget(sec)
    """

    def __init__(self, title, parent=None, expanded=True):
        super().__init__(parent)
        self._expanded = expanded
        self._build(title)

    def _build(self, title):
        outer = qt.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Toggle button acts as the section header
        self._toggle = qt.QPushButton()
        self._toggle.setCheckable(True)
        self._toggle.setChecked(self._expanded)
        self._toggle.setStyleSheet(
            "QPushButton { text-align:left; padding:5px 8px; "
            "background:#2c3e50; color:white; font-weight:bold; "
            "border-radius:4px; font-size:12px; }"
            "QPushButton:checked { background:#1a252f; }")
        self._toggle.toggled.connect(self._on_toggled)
        outer.addWidget(self._toggle)

        # Content container — shown or hidden based on toggle state
        self._content = qt.QWidget()
        content_lay = qt.QVBoxLayout(self._content)
        content_lay.setContentsMargins(4, 4, 4, 4)
        content_lay.setSpacing(4)
        self._contentLayout = content_lay
        self._content.setVisible(self._expanded)
        outer.addWidget(self._content)

        self._update_title(title)

    def _update_title(self, title):
        """Prepend ▼ or ▶ arrow to the header text."""
        arrow = "▼" if self._expanded else "▶"
        self._toggle.setText(f"  {arrow}  {title}")
        self._title = title

    def _on_toggled(self, checked):
        """Show or hide content when the header is clicked."""
        self._expanded = checked
        self._content.setVisible(checked)
        self._update_title(self._title)

    # Convenience pass-through methods so callers don't need to know the
    # internal layout structure
    def contentLayout(self):
        return self._contentLayout

    def addWidget(self, w):
        self._contentLayout.addWidget(w)

    def addLayout(self, lay):
        self._contentLayout.addLayout(lay)

    def setTitle(self, title):
        self._title = title
        self._update_title(title)


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — SIZE BAR CHART WIDGET
# ═══════════════════════════════════════════════════════════════════════════════

class SizeBarChart(qt.QWidget):
    """
    Inline bar chart showing the voxel count of each detected component.

    Visual encoding:
        Green bar  = component classified as a valid screw
        Red bar    = component below the artifact threshold
        Dashed line = current threshold value

    Interaction:
        Click a bar → emits barClicked(int index) signal
                    → slice views jump to that component's centroid
        Hover       → bar lightens for feedback
    """

    # Signal emitted with the 0-based component index when a bar is clicked
    barClicked = qt.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sizes     = []    # list of voxel counts (one per component)
        self._threshold = 0     # current absolute threshold value
        self._hovered   = -1    # index of bar under the mouse (-1 = none)
        self.setFixedHeight(75)
        self.setMouseTracking(True)
        self.setCursor(qt.Qt.PointingHandCursor)
        self.setToolTip(
            "Green=valid  Red=artifact\n"
            "Click a bar to jump slice views there.")

    def setData(self, sizes, threshold):
        """Update data and trigger a repaint."""
        self._sizes     = sizes
        self._threshold = threshold
        self.update()

    def _bar_rect(self, i, W, H, pl, pr, pt, pb):
        """Return (x, y, width, height) of bar i in pixel coordinates."""
        cw = W - pl - pr          # chart width in pixels
        ch = H - pt - pb          # chart height in pixels
        mx = max(self._sizes) or 1
        n  = len(self._sizes)
        bw = max(2, int(cw / n) - 2)           # bar width with gap
        bh = int(ch * self._sizes[i] / mx)     # bar height proportional to size
        bx = pl + i * (cw // n)               # bar left edge
        by = pt + ch - bh                      # bar top edge (y grows downward)
        return bx, by, bw, bh

    def paintEvent(self, event):
        """Draw bars, threshold line, and axis labels."""
        if not self._sizes:
            return

        p = qt.QPainter(self)
        p.setRenderHint(qt.QPainter.Antialiasing)
        W, H            = self.width, self.height
        pl, pr, pt, pb  = 6, 6, 6, 16      # padding: left/right/top/bottom
        ch              = H - pt - pb
        mx              = max(self._sizes) or 1

        # Background
        p.fillRect(0, 0, W, H, qt.QColor("#1a1a1a"))

        # Bars — green for valid, red for artifact, lighter when hovered
        for i, sz in enumerate(self._sizes):
            bx, by, bw, bh = self._bar_rect(i, W, H, pl, pr, pt, pb)
            c = qt.QColor("#e74c3c" if sz <= self._threshold else "#2ecc71")
            if i == self._hovered:
                c = c.lighter(140)
            p.fillRect(bx, by, bw, bh, c)

        # Dashed horizontal threshold line
        if self._threshold > 0:
            ty  = pt + ch - int(ch * self._threshold / mx)
            pen = qt.QPen(qt.QColor("#f9e79f"))
            pen.setStyle(qt.Qt.DashLine)
            pen.setWidth(1)
            p.setPen(pen)
            p.drawLine(pl, ty, W - pr, ty)
            p.setPen(qt.QColor("#f9e79f"))
            p.setFont(qt.QFont("Arial", 7))
            p.drawText(W - pr - 60, ty - 1, f"thr={self._threshold:.0f}")

        # X-axis: first and last component index
        p.setPen(qt.QColor("#888"))
        p.setFont(qt.QFont("Arial", 7))
        p.drawText(pl, H - 2, "1")
        p.drawText(W - pr - 8, H - 2, str(len(self._sizes)))
        p.end()

    def mouseMoveEvent(self, e):
        """Update hovered bar index and repaint."""
        idx = self._bar_at(e.x())
        if idx != self._hovered:
            self._hovered = idx
            self.update()

    def mousePressEvent(self, e):
        """Emit barClicked signal when a bar is clicked."""
        idx = self._bar_at(e.x())
        if idx >= 0:
            self.barClicked.emit(idx)

    def leaveEvent(self, e):
        """Clear hover when the mouse leaves the widget."""
        self._hovered = -1
        self.update()

    def _bar_at(self, mx):
        """Return the component index (0-based) at pixel x, or -1."""
        if not self._sizes:
            return -1
        W   = self.width
        pl  = pr = 6
        cw  = W - pl - pr
        n   = len(self._sizes)
        sw  = cw // n if n else 1   # slot width per bar
        col = (mx - pl) // sw
        return col if 0 <= col < n else -1


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 8 — MAIN DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class ScrewFiducialDialog(qt.QDialog):
    """
    Four-step GUI dialog for the screw fiducial pipeline.

    Step 1 — Select segmentation node and segment name.
    Step 2 — Identify isolated screw volumes via connected components;
             inspect sizes, detect artifacts, preview centroids in scene.
    Step 3 — Run PCA pipeline and create ScrewTips / ScrewCentroids nodes.
    Step 4 — Fine-tune each tip position with ± mm buttons per RAS axis.

    The dialog wraps all steps in a QScrollArea so it fits on any screen.
    Each step is a CollapsibleSection — click the header to expand/collapse.
    Step 4 is disabled until Step 3 completes successfully.
    """

    def __init__(self):
        super().__init__(slicer.util.mainWindow())
        self.setWindowTitle("Screw Fiducial Marker Generator")
        self.setMinimumWidth(540)

        # Cap dialog height to 85% of available screen space.
        # QDesktopWidget is used instead of QApplication.primaryScreen()
        # because Slicer's PythonQt binding does not expose primaryScreen().
        screen = qt.QDesktopWidget().availableGeometry()
        self.setMaximumHeight(int(screen.height() * 0.85))

        # ── Internal state ─────────────────────────────────────────────────
        self._labeled          = None   # labeled component array from Step 2
        self._ijkToRas         = None   # IJK→RAS matrix from labelmap
        self._n_screws         = 0      # total component count (incl. artifacts)
        self._sizes            = []     # voxel count per component
        self._centroids_ras    = []     # RAS centroid per component (for preview)
        self._labelmapNode     = None   # temporary labelmap node
        self._tipsNode         = None   # ScrewTips markup node (after Step 3)
        self._original_tips    = {}     # {index: np.array} for reset in Step 4
        self._previewScrewNode = None   # green preview markers (Step 2 toggle)
        self._previewArtNode   = None   # red artifact preview markers

        self._build_ui()
        self._populate_nodes()

    # ─────────────────────────────────────────────────────────────────────────
    #  UI CONSTRUCTION
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        """
        Build the outer dialog layout:
            [title label]
            [QScrollArea containing Steps 1-4]
            [Close button]
        All step content lives inside the scroll area so the dialog
        remains usable even on small monitors.
        """
        outer = qt.QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        title = qt.QLabel("🔩  Screw Fiducial Marker Generator")
        title.setStyleSheet(
            "font-size:14px; font-weight:bold; padding:4px;")
        outer.addWidget(title)

        # Scroll area — contains all collapsible step sections
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.NoFrame)

        container = qt.QWidget()
        self._mainLayout = qt.QVBoxLayout(container)
        self._mainLayout.setSpacing(6)
        self._mainLayout.setContentsMargins(2, 2, 2, 2)

        self._build_step1()
        self._build_step2()
        self._build_step3()
        self._build_step4()
        self._mainLayout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

        # Close button always visible outside the scroll area
        closeBtn = qt.QPushButton("Close")
        closeBtn.setStyleSheet("padding:6px; border-radius:4px;")
        closeBtn.clicked.connect(self._on_close)
        outer.addWidget(closeBtn)

    def _build_step1(self):
        """
        Step 1: dropdowns to select the segmentation node and segment name.
        The segment combo is repopulated whenever the node combo changes.
        """
        self._sec1 = CollapsibleSection(
            "Step 1 — Select segmentation", expanded=True)

        form = qt.QWidget()
        lay  = qt.QFormLayout(form)
        lay.setContentsMargins(0, 0, 0, 0)

        # Node combo — lists all vtkMRMLSegmentationNode in the scene
        self.segNodeCombo = qt.QComboBox()
        self.segNodeCombo.currentIndexChanged.connect(self._on_node_changed)
        lay.addRow("Segmentation node:", self.segNodeCombo)

        # Segment combo — lists segments within the selected node
        self.segNameCombo = qt.QComboBox()
        lay.addRow("Segment name:", self.segNameCombo)

        self.step1Info = qt.QLabel("")
        self.step1Info.setStyleSheet("color:gray; font-size:10px;")
        lay.addRow(self.step1Info)

        self._sec1.addWidget(form)
        self._mainLayout.addWidget(self._sec1)

    def _build_step2(self):
        """
        Step 2: identify isolated screw volumes.

        Contains:
        - Identify button → runs connected component analysis
        - Threshold slider → adjusts % of median for artifact detection
          (updates bar chart and table live without re-running identify)
        - Bar chart → visual size distribution; click to jump to centroid
        - Summary banner → total / valid / artifact counts
        - Warning banner → shown when artifacts are detected
        - Preview button → toggles centroid markers in the 3D/2D views
        - Table → one row per component with voxel count, % median,
                   classification and clickable jump column
        """
        self._sec2 = CollapsibleSection(
            "Step 2 — Identify individual screws", expanded=True)

        # ── Identify button ───────────────────────────────────────────────
        self.identifyBtn = qt.QPushButton(
            "🔍  Identify Screws (connected components)")
        self.identifyBtn.setStyleSheet(
            "background-color:#1e8449; color:white; "
            "font-weight:bold; padding:6px; border-radius:4px;")
        self.identifyBtn.clicked.connect(self._on_identify)
        self._sec2.addWidget(self.identifyBtn)

        # ── Threshold controls (hidden until after identify) ───────────────
        self.thrWidget = qt.QWidget()
        thrLay = qt.QVBoxLayout(self.thrWidget)
        thrLay.setContentsMargins(0, 2, 0, 0)
        thrLay.setSpacing(3)

        explLbl = qt.QLabel(
            "Volumes much smaller than the <b>median size</b> are "
            "auto-flagged as artifacts. Adjust sensitivity:")
        explLbl.setWordWrap(True)
        explLbl.setStyleSheet("font-size:10px; color:#aaa;")
        thrLay.addWidget(explLbl)

        slRow = qt.QHBoxLayout()
        slRow.addWidget(qt.QLabel("Flag if <"))

        # Slider range 1–80 % of median; default 20 %
        self.pctSlider = qt.QSlider(qt.Qt.Horizontal)
        self.pctSlider.setRange(1, 80)
        self.pctSlider.setValue(DEFAULT_PCT)
        self.pctSlider.setTickInterval(10)
        self.pctSlider.setTickPosition(qt.QSlider.TicksBelow)
        self.pctSlider.valueChanged.connect(self._on_threshold_changed)
        slRow.addWidget(self.pctSlider)

        self.pctLabel = qt.QLabel(f"{DEFAULT_PCT}% of median")
        self.pctLabel.setFixedWidth(100)
        self.pctLabel.setStyleSheet("font-weight:bold; color:#f9e79f;")
        slRow.addWidget(self.pctLabel)
        thrLay.addLayout(slRow)

        # Shows computed absolute threshold in voxels
        self.absThreshLabel = qt.QLabel("")
        self.absThreshLabel.setStyleSheet("font-size:10px; color:gray;")
        self.absThreshLabel.setWordWrap(True)
        thrLay.addWidget(self.absThreshLabel)

        self.thrWidget.hide()
        self._sec2.addWidget(self.thrWidget)

        # ── Bar chart ──────────────────────────────────────────────────────
        self.barChart = SizeBarChart()
        self.barChart.barClicked.connect(self._on_bar_clicked)
        self.barChart.hide()
        self._sec2.addWidget(self.barChart)

        # ── Summary banner ─────────────────────────────────────────────────
        self.summaryLabel = qt.QLabel("")
        self.summaryLabel.setStyleSheet(
            "font-size:11px; font-weight:bold; padding:4px; "
            "border-radius:3px;")
        self.summaryLabel.setWordWrap(True)
        self.summaryLabel.hide()
        self._sec2.addWidget(self.summaryLabel)

        # ── Warning banner (shown only when artifacts exist) ───────────────
        self.warnLabel = qt.QLabel("")
        self.warnLabel.setStyleSheet(
            "background:#7d3c00; color:#f9e79f; font-size:10px; "
            "font-weight:bold; padding:5px; border-radius:3px;")
        self.warnLabel.setWordWrap(True)
        self.warnLabel.hide()
        self._sec2.addWidget(self.warnLabel)

        # ── Preview button — toggles centroid markers in scene ─────────────
        self.previewBtn = qt.QPushButton(
            "👁  Show centroids in scene  (green=screw / red=artifact)")
        self.previewBtn.setStyleSheet(
            "background-color:#5d4e8c; color:white; "
            "font-weight:bold; padding:5px; border-radius:4px;")
        self.previewBtn.setCheckable(True)
        self.previewBtn.toggled.connect(self._on_preview_toggled)
        self.previewBtn.hide()
        self._sec2.addWidget(self.previewBtn)

        # ── Per-component table ────────────────────────────────────────────
        # Columns: Volume label | Voxels | % of median | Classification | Jump
        self.screwTable = qt.QTableWidget(0, 5)
        self.screwTable.setHorizontalHeaderLabels(
            ["Volume", "Voxels", "% median", "Classification", "Jump"])
        self.screwTable.horizontalHeader().setStretchLastSection(False)
        self.screwTable.setEditTriggers(qt.QTableWidget.NoEditTriggers)
        self.screwTable.setSelectionBehavior(qt.QTableWidget.SelectRows)
        self.screwTable.setMaximumHeight(160)
        # Clicking any cell in a row jumps slice views to that component
        self.screwTable.cellClicked.connect(self._on_table_cell_clicked)
        self.screwTable.hide()
        self._sec2.addWidget(self.screwTable)

        self.step2Info = qt.QLabel("")
        self.step2Info.setStyleSheet("color:gray; font-size:10px;")
        self._sec2.addWidget(self.step2Info)

        self._mainLayout.addWidget(self._sec2)

    def _build_step3(self):
        """
        Step 3: single button to run the PCA pipeline.
        Button is disabled until Step 2 has been run successfully.
        After completion the button re-enables and Step 4 unlocks.
        """
        self._sec3 = CollapsibleSection(
            "Step 3 — Compute fiducial markers", expanded=True)

        self.runBtn = qt.QPushButton("▶  Compute Fiducials")
        self.runBtn.setStyleSheet(
            "background-color:#2e86c1; color:white; "
            "font-weight:bold; padding:6px; border-radius:4px;")
        self.runBtn.setEnabled(False)   # requires Step 2 first
        self.runBtn.clicked.connect(self._on_run)
        self._sec3.addWidget(self.runBtn)

        self.step3Info = qt.QLabel("  ℹ  Run Step 2 first.")
        self.step3Info.setStyleSheet("color:gray; font-size:10px;")
        self._sec3.addWidget(self.step3Info)

        self._mainLayout.addWidget(self._sec3)

    def _build_step4(self):
        """
        Step 4: manual fine-tuning of tip positions.

        Controls:
        - Screw selector dropdown (jumping slice views on change)
        - Step size spinbox in mm
        - RAS axis ± buttons (one row per axis, colour-coded)
        - Position display (RAS coordinates, monospace)
        - Reset button (restores originally computed position)

        The section header is disabled until Step 3 completes.
        """
        self._sec4 = CollapsibleSection(
            "Step 4 — Fine-tune tip positions", expanded=False)

        # ── Screw selector + step size ─────────────────────────────────────
        selRow = qt.QHBoxLayout()
        selRow.addWidget(qt.QLabel("Screw:"))

        self.screwSelector = qt.QComboBox()
        self.screwSelector.setMinimumWidth(120)
        # Changing the selected screw jumps slice views to its tip
        self.screwSelector.currentIndexChanged.connect(
            self._on_screw_selected)
        selRow.addWidget(self.screwSelector)
        selRow.addSpacing(10)
        selRow.addWidget(qt.QLabel("Step (mm):"))

        self.stepSpin = qt.QDoubleSpinBox()
        self.stepSpin.setRange(0.01, 20.0)
        self.stepSpin.setSingleStep(0.5)
        self.stepSpin.setValue(1.0)
        self.stepSpin.setDecimals(2)
        self.stepSpin.setFixedWidth(65)
        selRow.addWidget(self.stepSpin)
        selRow.addStretch()
        self._sec4.addLayout(selRow)

        # ── Current position display ───────────────────────────────────────
        self.posLabel = qt.QLabel("Position (RAS):  —")
        self.posLabel.setStyleSheet(
            "font-family:monospace; font-size:11px; padding:3px; "
            "background:#1a1a1a; color:#00ff99; border-radius:3px;")
        self._sec4.addWidget(self.posLabel)

        # ── Axis ± buttons ─────────────────────────────────────────────────
        # One row per RAS axis: [axis label] [− button] [+ button]
        axes_widget = qt.QWidget()
        ag = qt.QGridLayout(axes_widget)
        ag.setSpacing(4)
        ag.setContentsMargins(0, 0, 0, 0)
        for col, hdr in enumerate(["Axis", "−", "+"]):
            lbl = qt.QLabel(f"<b>{hdr}</b>")
            lbl.setAlignment(qt.Qt.AlignCenter)
            ag.addWidget(lbl, 0, col)

        self._axis_btns = []
        for row, (lbl_text, ax_idx, color) in enumerate(AXES, 1):
            lbl = qt.QLabel(f"<b>{lbl_text}</b>")
            lbl.setStyleSheet(f"color:{color};")
            lbl.setAlignment(qt.Qt.AlignCenter)
            ag.addWidget(lbl, row, 0)

            style = (f"background:{color}; color:white; font-weight:bold; "
                     f"font-size:14px; padding:4px 14px; "
                     f"border-radius:3px; min-width:60px;")

            # Minus: move tip in the negative direction along this axis
            bm = qt.QPushButton("−")
            bm.setStyleSheet(style)
            bm.clicked.connect(
                lambda _, ax=ax_idx: self._move_tip(ax, -1))
            ag.addWidget(bm, row, 1)

            # Plus: move tip in the positive direction
            bp = qt.QPushButton("+")
            bp.setStyleSheet(style)
            bp.clicked.connect(
                lambda _, ax=ax_idx: self._move_tip(ax, +1))
            ag.addWidget(bp, row, 2)
            self._axis_btns.append((bm, bp))

        self._sec4.addWidget(axes_widget)

        # ── Reset button ───────────────────────────────────────────────────
        resetBtn = qt.QPushButton("↺  Reset to computed position")
        resetBtn.setStyleSheet(
            "color:#e67e22; padding:4px; border-radius:3px;")
        resetBtn.clicked.connect(self._on_reset_tip)
        self._sec4.addWidget(resetBtn)

        # Section header disabled until Step 3 finishes
        self._sec4._toggle.setEnabled(False)

        self._mainLayout.addWidget(self._sec4)

    # ─────────────────────────────────────────────────────────────────────────
    #  PREVIEW NODE HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_all_centroids(self):
        """
        Pre-compute the RAS centroid of every connected component.
        Called once after identify_screws() so centroids are available
        for the jump-to and preview features without re-running the export.
        """
        self._centroids_ras = []
        for comp_id in range(1, self._n_screws + 1):
            idx    = np.argwhere(self._labeled == comp_id)
            coords = voxels_to_ras(idx, self._ijkToRas)
            self._centroids_ras.append(coords.mean(axis=0))

    def _remove_preview_nodes(self):
        """Remove temporary preview markup nodes from the scene if they exist."""
        for attr in ("_previewScrewNode", "_previewArtNode"):
            node = getattr(self, attr, None)
            if node:
                try:
                    slicer.mrmlScene.RemoveNode(node)
                except Exception:
                    pass
                setattr(self, attr, None)

    def _build_preview_nodes(self):
        """
        Create two markup nodes showing centroids of all components:
            PREVIEW_ValidScrews — green cross glyphs
            PREVIEW_Artifacts   — red starburst glyphs (larger, easier to spot)
        Both are grouped under a Subject Hierarchy folder.
        Labels include the voxel count so the user can identify which
        component to erase in Segment Editor.
        """
        self._remove_preview_nodes()
        abs_thr, _ = compute_auto_threshold(
            self._sizes, self.pctSlider.value)

        # Valid screw preview node — small green crosses
        screwNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode", "PREVIEW_ValidScrews")
        dn = screwNode.GetDisplayNode()
        dn.SetColor(0.0, 0.9, 0.3)
        dn.SetSelectedColor(0.0, 0.9, 0.3)
        dn.SetGlyphScale(1.5)
        dn.SetTextScale(2.0)
        dn.SetGlyphType(slicer.vtkMRMLMarkupsDisplayNode.Cross2D)

        # Artifact preview node — large red starbursts
        artNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode", "PREVIEW_Artifacts")
        dn = artNode.GetDisplayNode()
        dn.SetColor(1.0, 0.1, 0.1)
        dn.SetSelectedColor(1.0, 0.5, 0.0)
        dn.SetGlyphScale(3.0)   # intentionally large so artifacts are obvious
        dn.SetTextScale(3.0)
        dn.SetGlyphType(slicer.vtkMRMLMarkupsDisplayNode.StarBurst2D)

        for i, (sz, ctr) in enumerate(
                zip(self._sizes, self._centroids_ras)):
            is_art = sz <= abs_thr
            node   = artNode if is_art else screwNode
            label  = (f"⚠ART_{i+1:02d}({sz}vx)"
                      if is_art else f"Vol_{i+1:02d}({sz}vx)")
            idx = node.AddControlPoint(ctr.tolist())
            node.SetNthControlPointLabel(idx, label)
            node.SetNthControlPointLocked(idx, True)   # not interactive

        self._previewScrewNode = screwNode
        self._previewArtNode   = artNode
        group_nodes_in_folder("PREVIEW_Volumes", [screwNode, artNode])

    def _on_preview_toggled(self, checked):
        """Show or hide centroid preview nodes when the button is toggled."""
        self.previewBtn.setText(
            "👁  Hide centroids" if checked
            else "👁  Show centroids in scene  (green=screw / red=artifact)")
        if checked:
            self._build_preview_nodes()
        else:
            self._remove_preview_nodes()

    def _jump_to_centroid(self, comp_idx):
        """
        Jump all slice views to the centroid of component comp_idx (0-based).
        Uses a temporary markup node to drive the JumpSlicesToNthPointInMarkup
        logic, then immediately removes it.
        """
        if not self._centroids_ras or comp_idx >= len(self._centroids_ras):
            return
        ctr = self._centroids_ras[comp_idx]
        tmp = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode", "__jmp__")
        idx = tmp.AddControlPoint(ctr.tolist())
        slicer.modules.markups.logic().JumpSlicesToNthPointInMarkup(
            tmp.GetID(), idx, True)
        slicer.mrmlScene.RemoveNode(tmp)

    # ─────────────────────────────────────────────────────────────────────────
    #  CALLBACKS — STEP 1
    # ─────────────────────────────────────────────────────────────────────────

    def _populate_nodes(self):
        """Fill the segmentation node combo with all nodes in the current scene."""
        self.segNodeCombo.clear()
        nodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        for n in nodes:
            self.segNodeCombo.addItem(n.GetName())
        if nodes:
            self._on_node_changed(0)

    def _on_node_changed(self, _):
        """
        When the node combo changes, repopulate the segment combo and
        reset any results from a previous identify run.
        """
        self.segNameCombo.clear()
        self._reset_identify()
        name = self.segNodeCombo.currentText
        if not name:
            return
        try:
            seg = slicer.util.getNode(name).GetSegmentation()
            n   = seg.GetNumberOfSegments()
            for i in range(n):
                self.segNameCombo.addItem(seg.GetNthSegment(i).GetName())
            self.step1Info.setText(f"  {n} Slicer segment(s) found")
        except Exception as e:
            self.step1Info.setText(f"  Error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    #  CALLBACKS — STEP 2
    # ─────────────────────────────────────────────────────────────────────────

    def _reset_identify(self):
        """
        Clear all state from a previous identify run and hide all
        Step-2 result widgets. Called when node selection changes or
        when the dialog is closed.
        """
        self._remove_preview_nodes()
        if self._labelmapNode:
            try:
                slicer.mrmlScene.RemoveNode(self._labelmapNode)
            except Exception:
                pass
        self._labeled       = None
        self._ijkToRas      = None
        self._n_screws      = 0
        self._sizes         = []
        self._centroids_ras = []
        self._labelmapNode  = None
        self.runBtn.setEnabled(False)
        self.step3Info.setText("  ℹ  Run Step 2 first.")
        self.screwTable.setRowCount(0)
        self.screwTable.hide()
        self.summaryLabel.hide()
        self.warnLabel.hide()
        self.barChart.hide()
        self.thrWidget.hide()
        self.previewBtn.setChecked(False)
        self.previewBtn.hide()

    def _on_identify(self):
        """
        Run connected component analysis on the selected segment.
        Populates the table, bar chart and banners.
        Centroids are pre-computed here and reused in preview/jump/pipeline.
        The labelmap node is kept alive until run_pipeline() removes it.
        """
        seg_node    = self.segNodeCombo.currentText
        seg_segment = self.segNameCombo.currentText
        if not seg_node or not seg_segment:
            slicer.util.errorDisplay("Select a node and segment first.")
            return

        self._reset_identify()
        self.identifyBtn.setText("⏳  Identifying...")
        self.identifyBtn.setEnabled(False)
        qt.QApplication.processEvents()   # allow UI to update before blocking

        try:
            labeled, ijkToRas, n, sizes, labelmapNode = \
                identify_screws(seg_node, seg_segment)
            self._labeled      = labeled
            self._ijkToRas     = ijkToRas
            self._n_screws     = n
            self._sizes        = sizes
            self._labelmapNode = labelmapNode   # kept for run_pipeline()

            # Pre-compute centroids once; used by jump, preview, and pipeline
            self._compute_all_centroids()

            # Populate table — colours set by _refresh()
            self.screwTable.setRowCount(n)
            for i, sz in enumerate(sizes):
                for col, val in enumerate(
                        [f"Vol_{i+1:02d}", str(sz), "", "", "📍"]):
                    item = qt.QTableWidgetItem(val)
                    item.setTextAlignment(qt.Qt.AlignCenter)
                    if col == 4:   # Jump column in blue
                        item.setForeground(qt.QColor("#3498db"))
                    self.screwTable.setItem(i, col, item)

            self.screwTable.resizeColumnsToContents()
            self.screwTable.show()
            self.thrWidget.show()
            self.barChart.show()
            self.previewBtn.show()
            self.runBtn.setEnabled(True)
            self._refresh()   # compute threshold and update all colours

        except Exception as e:
            slicer.util.errorDisplay(f"Identify failed:\n{e}")
        finally:
            self.identifyBtn.setText(
                "🔍  Identify Screws (connected components)")
            self.identifyBtn.setEnabled(True)

    def _on_threshold_changed(self, value):
        """
        Called when the slider moves.
        Updates the percentage label, recomputes colours/banners live,
        and rebuilds preview nodes if they are currently visible.
        """
        self.pctLabel.setText(f"{value}% of median")
        self._refresh()
        if self.previewBtn.isChecked():
            self._build_preview_nodes()   # rebuild with new threshold

    def _refresh(self):
        """
        Recompute the artifact threshold from the current slider value and
        update all dependent UI elements:
            - absThreshLabel (shows computed voxel count)
            - bar chart      (threshold line position + bar colours)
            - table rows     (% of median column + classification + row bg)
            - summary banner (counts)
            - warning banner (shown/hidden based on artifact count)
            - step3Info      (ready message or warning)
        This runs without re-exporting the labelmap — pure UI update.
        """
        if not self._sizes:
            return

        pct = self.pctSlider.value
        abs_thr, median = compute_auto_threshold(self._sizes, pct)

        # Show the computed absolute threshold so the user understands it
        self.absThreshLabel.setText(
            f"Median={median:.0f} vx  →  threshold={abs_thr:.0f} vx "
            f"({pct}% × {median:.0f})")

        self.barChart.setData(self._sizes, abs_thr)

        n_art = n_valid = 0
        for i, sz in enumerate(self._sizes):
            pct_med  = (sz / median * 100) if median > 0 else 0
            is_art   = sz < abs_thr
            cls_text = "⚠  Artifact" if is_art else "✓  Screw"
            fg       = qt.QColor("#e74c3c" if is_art else "#2ecc71")
            bg       = qt.QColor("#3d0000" if is_art else "transparent")
            if is_art:
                n_art  += 1
            else:
                n_valid += 1

            # Update % median and classification columns only (cols 2 and 3)
            for col, val in enumerate([None, None,
                                       f"{pct_med:.0f}%", cls_text, None]):
                if val is None:
                    continue
                item = qt.QTableWidgetItem(val)
                item.setTextAlignment(qt.Qt.AlignCenter)
                if col == 3:
                    item.setForeground(fg)
                self.screwTable.setItem(i, col, item)

            # Row background colour
            for col in range(5):
                item = self.screwTable.item(i, col)
                if item:
                    item.setBackground(bg)

        # Summary banner
        self.summaryLabel.setText(
            f"📊 {len(self._sizes)} volumes   ✓ {n_valid} screws   "
            f"⚠ {n_art} artifacts   median {int(median)} vx")

        if n_art > 0:
            self.summaryLabel.setStyleSheet(
                "background:#2d1a00; color:#f9e79f; font-size:11px; "
                "font-weight:bold; padding:4px; border-radius:3px;")
            self.warnLabel.setText(
                f"⚠  {n_art} artifact(s) found.\n"
                f"Click a row or bar to locate them. "
                f"Enable 'Show centroids' to see them in 3D.\n"
                f"Then use Segment Editor → Erase/Islands to remove them.")
            self.warnLabel.show()
            self.step3Info.setText(
                f"  ⚠  {n_art} artifact(s) will be skipped. "
                f"{n_valid} fiducials will be created.")
        else:
            self.summaryLabel.setStyleSheet(
                "background:#0d2d0d; color:#2ecc71; font-size:11px; "
                "font-weight:bold; padding:4px; border-radius:3px;")
            self.warnLabel.hide()
            self.step3Info.setText(
                f"  ✓  All {n_valid} volumes are valid screws.")
        self.summaryLabel.show()

    def _on_table_cell_clicked(self, row, _):
        """Jump slice views to the centroid of the clicked row's component."""
        self._jump_to_centroid(row)

    def _on_bar_clicked(self, idx):
        """Jump slice views to the centroid of the clicked bar's component."""
        self._jump_to_centroid(idx)

    # ─────────────────────────────────────────────────────────────────────────
    #  CALLBACKS — STEP 3
    # ─────────────────────────────────────────────────────────────────────────

    def _on_run(self):
        """
        Run the PCA pipeline on all valid components.
        If artifacts are present, ask the user to confirm before proceeding.
        On success: populates Step 4 selector and unlocks the Step 4 section.
        """
        if self._labeled is None:
            slicer.util.errorDisplay("Run Step 2 first.")
            return

        pct     = self.pctSlider.value
        abs_thr, _ = compute_auto_threshold(self._sizes, pct)
        n_art   = sum(1 for s in self._sizes if s < abs_thr)
        n_valid = len(self._sizes) - n_art

        # Warn if artifacts will be skipped; user can cancel and clean first
        if n_art > 0:
            ok = slicer.util.confirmYesNoDisplay(
                f"⚠  {n_art} artifact(s) will be skipped.\n"
                f"{n_valid} fiducials will be created.\nProceed?",
                windowTitle="Artifacts detected")
            if not ok:
                return

        # Remove preview centroids before creating the real output nodes
        self._remove_preview_nodes()
        self.previewBtn.setChecked(False)

        self.runBtn.setText("⏳  Computing...")
        self.runBtn.setEnabled(False)
        qt.QApplication.processEvents()

        try:
            results, tipsNode = run_pipeline(
                self._labeled, self._ijkToRas,
                self._n_screws, self._sizes,
                abs_thr, self._labelmapNode)

            self._labelmapNode  = None   # removed inside run_pipeline()
            self._tipsNode      = tipsNode

            # Store original computed positions so Step 4 can reset them
            self._original_tips = {i: r["tip"].copy()
                                   for i, r in enumerate(results)}

            self._populate_tune_panel(results)
            self.step3Info.setText(
                f"  ✓  {len(results)} markers created.")

            # Unlock and auto-expand Step 4 section
            self._sec4._toggle.setEnabled(True)
            self._sec4._toggle.setChecked(True)
            self._sec4._on_toggled(True)

        except Exception as e:
            slicer.util.errorDisplay(f"Compute failed:\n{e}")
        finally:
            self.runBtn.setText("▶  Compute Fiducials")
            self.runBtn.setEnabled(True)

    # ─────────────────────────────────────────────────────────────────────────
    #  CALLBACKS — STEP 4
    # ─────────────────────────────────────────────────────────────────────────

    def _populate_tune_panel(self, results):
        """Fill the screw selector combo after Step 3 and select the first."""
        self.screwSelector.blockSignals(True)
        self.screwSelector.clear()
        for r in results:
            self.screwSelector.addItem(r["name"])
        self.screwSelector.blockSignals(False)
        self.screwSelector.setCurrentIndex(0)
        self._on_screw_selected(0)

    def _on_screw_selected(self, index):
        """
        When the selected screw changes:
            - Read its current RAS position from the tips node
            - Update the position display label
            - Jump all slice views to that point
        """
        if self._tipsNode is None or index < 0:
            return
        pos = [0, 0, 0]
        self._tipsNode.GetNthControlPointPositionWorld(index, pos)
        self.posLabel.setText(
            f"R={pos[0]:+7.2f}  A={pos[1]:+7.2f}  S={pos[2]:+7.2f}  mm")
        slicer.modules.markups.logic().JumpSlicesToNthPointInMarkup(
            self._tipsNode.GetID(), index, True)

    def _move_tip(self, axis_idx, direction):
        """
        Move the currently selected tip by ± step mm along one RAS axis.

        Parameters
        ----------
        axis_idx : int
            0 = R, 1 = A, 2 = S
        direction : int
            +1 (positive axis) or -1 (negative axis)
        """
        if self._tipsNode is None:
            return
        idx  = self.screwSelector.currentIndex
        step = self.stepSpin.value * direction

        pos = [0.0, 0.0, 0.0]
        self._tipsNode.GetNthControlPointPositionWorld(idx, pos)
        pos[axis_idx] += step
        self._tipsNode.SetNthControlPointPositionWorld(idx, *pos)

        # Refresh the position display and slice jump
        self._on_screw_selected(idx)

    def _on_reset_tip(self):
        """Restore the selected tip to its originally computed position."""
        if self._tipsNode is None:
            return
        idx = self.screwSelector.currentIndex
        if idx in self._original_tips:
            o = self._original_tips[idx]
            self._tipsNode.SetNthControlPointPositionWorld(
                idx, o[0], o[1], o[2])
            self._on_screw_selected(idx)

    def _on_close(self):
        """Clean up preview nodes and temporary state before closing."""
        self._remove_preview_nodes()
        self._reset_identify()
        self.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

dialog = ScrewFiducialDialog()
dialog.show()
