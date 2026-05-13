"""
unity_segmentation_exporter.py
──────────────────────────────────────────────────────────────────────────────
Non-blocking 3D Slicer GUI to export segmentations and model nodes as
Unity-ready OBJ + MTL files.

Exports are configured for direct import into Unity:
  • Coordinate system  : LPS (default) — compatible with a Unity parent
                         transform that has Rotation(-180°, 0, 0).
  • Output units       : Metres (default) — Unity's native unit; the parent
                         GameObject scale can be set to 1.
  • Smoothing          : Windowed-Sinc filter removes marching-cubes artefacts.
  • Decimation         : Quadric decimation reduces triangle count (adjustable).
  • Material export    : .mtl file carries the Slicer segment colour as Kd;
                         Unity auto-creates a Material on import.
  • Double-sided       : Optional; duplicates triangles with reversed normals
                         for open surfaces (e.g. Virtual Fixtures).
  • World-space baking : All parent MRML transforms are baked into vertices
                         so exported meshes are aligned in world RAS before
                         the LPS conversion.
  • Non-blocking GUI   : QTimer.singleShot-driven export queue keeps Slicer
                         responsive; progress bar updates live.

Usage
─────
    Open the Python Console (Ctrl+3) and run:
        exec(open(r"path\\to\\unity_segmentation_exporter.py").read())

──────────────────────────────────────────────────────────────────────────────
"""

import slicer
import qt
import vtk
import os


class ExportForUnityDialog(qt.QDialog):

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  CONSTRUCTOR + LAYOUT                                                ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Export Models for Unity")
        self.setModal(False)              # non-modal: keep Slicer interactive
        self.resize(620, 760)
        self._center_on_screen()
        self._build_ui()
        self._refresh_items()

    def _center_on_screen(self):
        try:
            screen = qt.QDesktopWidget().availableGeometry()
            x = (screen.width()  - self.width)  // 2
            y = (screen.height() - self.height) // 2
            self.move(x, y)
        except Exception:
            pass

    def _build_ui(self):
        layout = qt.QVBoxLayout(self)

        # ── Header ───────────────────────────────────────────────────────────
        header = qt.QLabel(
            "<b>Export Slicer segmentations &amp; models for Unity</b><br>"
            "<i>Defaults: LPS coordinates, metres. Ready for Unity import.</i>")
        header.setWordWrap(True)
        layout.addWidget(header)

        # ── Source items ─────────────────────────────────────────────────────
        srcGroup = qt.QGroupBox("Items to Export")
        srcLayout = qt.QVBoxLayout(srcGroup)

        toolbar = qt.QHBoxLayout()
        self.refreshBtn      = qt.QPushButton("⟳ Refresh")
        self.selectAllBtn    = qt.QPushButton("Select All")
        self.deselectAllBtn  = qt.QPushButton("Clear")
        self.refreshBtn.connect(     "clicked()", self._refresh_items)
        self.selectAllBtn.connect(   "clicked()", lambda: self._set_all(True))
        self.deselectAllBtn.connect( "clicked()", lambda: self._set_all(False))
        toolbar.addWidget(self.refreshBtn)
        toolbar.addWidget(self.selectAllBtn)
        toolbar.addWidget(self.deselectAllBtn)
        toolbar.addStretch()
        srcLayout.addLayout(toolbar)

        # Parallel data store — keyed by row index instead of item.data(UserRole)
        # to avoid the PythonQt UserRole-tuple lifetime issues that can crash
        # Slicer when items are clicked on some Qt5 builds.
        self._row_payloads = []

        self.itemList = qt.QListWidget()
        # MultiSelection (not NoSelection): NoSelection + checkable items is the
        # combination that triggers Slicer crashes on click. MultiSelection plays
        # nicely with checkable items and does not freeze the event loop.
        self.itemList.setSelectionMode(qt.QAbstractItemView.MultiSelection)
        self.itemList.setUniformItemSizes(True)
        self.itemList.connect("itemClicked(QListWidgetItem*)", self._on_item_clicked)
        srcLayout.addWidget(self.itemList)

        layout.addWidget(srcGroup)

        # ── Output folder & prefix ───────────────────────────────────────────
        outGroup = qt.QGroupBox("Output")
        outForm  = qt.QFormLayout(outGroup)

        folderRow = qt.QHBoxLayout()
        self.folderEdit = qt.QLineEdit(slicer.app.temporaryPath)
        browseBtn = qt.QPushButton("Browse…")
        browseBtn.connect("clicked()", self._on_browse)
        folderRow.addWidget(self.folderEdit)
        folderRow.addWidget(browseBtn)
        outForm.addRow("Folder:", folderRow)

        self.prefixEdit = qt.QLineEdit()
        self.prefixEdit.setPlaceholderText(
            "optional — prepended to each filename (e.g. 'Patient01_')")
        outForm.addRow("Filename prefix:", self.prefixEdit)

        layout.addWidget(outGroup)

        # ── Coord system & scale ─────────────────────────────────────────────
        coordGroup = qt.QGroupBox("Coordinate System & Scale")
        coordForm  = qt.QFormLayout(coordGroup)

        self.coordCombo = qt.QComboBox()
        self.coordCombo.addItems([
            "LPS — for Unity  (use with parent Rotation -180° X)",
            "RAS — for Slicer  (Slicer native; needs a different Unity parent)",
        ])
        coordForm.addRow("Coord system:", self.coordCombo)

        self.unitCombo = qt.QComboBox()
        self.unitCombo.addItems([
            "Metres — for Unity  (Unity native unit; parent scale = 1)",
            "Millimetres — for Slicer  (use with Unity parent scale 0.001)",
        ])
        coordForm.addRow("Output units:", self.unitCombo)

        layout.addWidget(coordGroup)

        # ── Mesh processing ──────────────────────────────────────────────────
        meshGroup  = qt.QGroupBox("Mesh Processing")
        meshLayout = qt.QVBoxLayout(meshGroup)

        # ─ Smoothing
        smoothRow = qt.QHBoxLayout()
        self.smoothCheck = qt.QCheckBox("Smooth (Windowed-Sinc)")
        self.smoothCheck.setChecked(True)
        smoothRow.addWidget(self.smoothCheck)
        smoothRow.addStretch()
        smoothRow.addWidget(qt.QLabel("Iterations:"))
        self.smoothIters = qt.QSpinBox()
        self.smoothIters.setMinimum(0)
        self.smoothIters.setMaximum(50)
        self.smoothIters.setValue(15)
        smoothRow.addWidget(self.smoothIters)
        meshLayout.addLayout(smoothRow)

        # ─ Decimation
        decRow = qt.QHBoxLayout()
        self.decimateCheck = qt.QCheckBox("Reduce triangle count")
        self.decimateCheck.setChecked(True)
        decRow.addWidget(self.decimateCheck)
        decRow.addStretch()
        decRow.addWidget(qt.QLabel("Reduction:"))
        self.decimateSlider = qt.QSlider(qt.Qt.Horizontal)
        self.decimateSlider.setMinimum(0)
        self.decimateSlider.setMaximum(95)
        self.decimateSlider.setValue(50)
        self.decimateSlider.setMinimumWidth(180)
        self.decimateValue  = qt.QLabel("50%")
        self.decimateValue.setMinimumWidth(40)
        self.decimateSlider.connect(
            "valueChanged(int)",
            lambda v: self.decimateValue.setText(f"{v}%"))
        decRow.addWidget(self.decimateSlider)
        decRow.addWidget(self.decimateValue)
        meshLayout.addLayout(decRow)

        # ─ Material
        self.matCheck = qt.QCheckBox(
            "Export with .mtl material file (segment / model color)")
        self.matCheck.setChecked(True)
        meshLayout.addWidget(self.matCheck)

        # ─ Double-sided
        self.doubleSidedCheck = qt.QCheckBox(
            "Double-sided  (duplicates triangles with reversed normals — "
            "use for open surfaces like Virtual Fixtures)")
        self.doubleSidedCheck.setChecked(False)
        meshLayout.addWidget(self.doubleSidedCheck)

        layout.addWidget(meshGroup)

        # ── Status & progress ────────────────────────────────────────────────
        self.statusLabel = qt.QLabel("Ready.")
        self.statusLabel.setWordWrap(True)
        self.statusLabel.setStyleSheet("padding: 6px;")
        layout.addWidget(self.statusLabel)

        self.progressBar = qt.QProgressBar()
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(0)
        layout.addWidget(self.progressBar)

        # ── Buttons ──────────────────────────────────────────────────────────
        btnRow = qt.QHBoxLayout()
        btnRow.addStretch()
        self.exportBtn = qt.QPushButton("⤓ Export Selected")
        self.exportBtn.connect("clicked()", self._on_export)
        self.exportBtn.setStyleSheet("font-weight: bold; padding: 8px 18px;")
        btnRow.addWidget(self.exportBtn)
        closeBtn = qt.QPushButton("Close")
        closeBtn.connect("clicked()", self.close)
        btnRow.addWidget(closeBtn)
        layout.addLayout(btnRow)

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  ITEM ENUMERATION                                                    ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _refresh_items(self):
        # Block signals during bulk update to avoid spurious itemChanged events
        self.itemList.blockSignals(True)
        try:
            self.itemList.clear()
            self._row_payloads = []

            # ─ Segments from segmentation nodes
            for node in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
                seg = node.GetSegmentation()
                if seg is None:
                    continue
                for i in range(seg.GetNumberOfSegments()):
                    sid = seg.GetNthSegmentID(i)
                    segment = seg.GetSegment(sid)
                    if segment is None:
                        continue
                    label = f"[Seg]   {node.GetName()} → {segment.GetName()}"
                    self._add_item(
                        label,
                        ('segment', node.GetID(), sid, segment.GetName()))

            # ─ Stand-alone model nodes (skip Slicer's internal slice models)
            skip_names = {"Red Volume Slice", "Green Volume Slice",
                          "Yellow Volume Slice"}
            for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
                if node.GetName() in skip_names:
                    continue
                label = f"[Model] {node.GetName()}"
                self._add_item(
                    label, ('model', node.GetID(), None, node.GetName()))
        finally:
            self.itemList.blockSignals(False)

        n = len(self._row_payloads)
        self.statusLabel.setText(f"Found {n} exportable item(s).")

    def _add_item(self, label, payload):
        # Store payload by row index (not in item.data) — avoids the PythonQt
        # UserRole tuple GC issue that destabilises Slicer on click.
        item = qt.QListWidgetItem(label)
        item.setFlags(qt.Qt.ItemIsUserCheckable
                      | qt.Qt.ItemIsEnabled
                      | qt.Qt.ItemIsSelectable)
        item.setCheckState(qt.Qt.Unchecked)
        self.itemList.addItem(item)
        self._row_payloads.append(payload)

    def _on_item_clicked(self, item):
        # Explicit toggle: clicking anywhere on the row flips the check state.
        # This replaces Qt's default click-on-checkbox-only behaviour, which
        # was unreliable in our list and tied to the unstable selection mode.
        if item is None:
            return
        new_state = (qt.Qt.Unchecked
                     if item.checkState() == qt.Qt.Checked
                     else qt.Qt.Checked)
        # Block signals while we change state to avoid recursion through any
        # itemChanged listeners Slicer/Qt may attach internally.
        self.itemList.blockSignals(True)
        item.setCheckState(new_state)
        self.itemList.blockSignals(False)

    def _set_all(self, checked):
        state = qt.Qt.Checked if checked else qt.Qt.Unchecked
        # Bulk operation: block signals for the whole loop
        self.itemList.blockSignals(True)
        try:
            for i in range(self.itemList.count):
                it = self.itemList.item(i)
                if it is not None:
                    it.setCheckState(state)
        finally:
            self.itemList.blockSignals(False)

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  EXPORT WORKFLOW (non-blocking via QTimer.singleShot)                ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _on_browse(self):
        folder = qt.QFileDialog.getExistingDirectory(
            self, "Select output folder", self.folderEdit.text)
        if folder:
            self.folderEdit.setText(folder)

    def _on_export(self):
        # ─ Collect checked items by row index → look up payload from parallel list
        selected = []
        for i in range(self.itemList.count):
            item = self.itemList.item(i)
            if item is None:
                continue
            if item.checkState() == qt.Qt.Checked and i < len(self._row_payloads):
                selected.append(self._row_payloads[i])

        if not selected:
            self.statusLabel.setText("⚠ Nothing selected.")
            return

        folder = self.folderEdit.text.strip()
        if not folder:
            self.statusLabel.setText("⚠ Choose an output folder.")
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            self.statusLabel.setText(f"⚠ Cannot create folder: {e}")
            return

        # ─ Snapshot context for the worker
        self._ctx = {
            'folder':            folder,
            'prefix':            self.prefixEdit.text.strip(),
            'coord_lps':         (self.coordCombo.currentIndex == 0),
            'scale':             0.001 if self.unitCombo.currentIndex == 0 else 1.0,
            'smooth':            self.smoothCheck.isChecked(),
            'smooth_iters':      self.smoothIters.value,
            'decimate':          self.decimateCheck.isChecked(),
            'decimate_target':   self.decimateSlider.value / 100.0,
            'with_mtl':          self.matCheck.isChecked(),
            'double_sided':      self.doubleSidedCheck.isChecked(),
        }
        self._queue    = list(selected)
        self._total    = len(selected)
        self._exported = 0
        self._errors   = []

        self.exportBtn.setEnabled(False)
        self.refreshBtn.setEnabled(False)
        self.progressBar.setValue(0)
        self.statusLabel.setText(f"Exporting 1/{self._total}…")

        qt.QTimer.singleShot(50, self._process_next)

    def _process_next(self):
        if not self._queue:
            self._on_export_done()
            return

        kind, node_id, sid, name = self._queue.pop(0)
        idx = self._exported + len(self._errors) + 1
        self.statusLabel.setText(f"[{idx}/{self._total}] Processing {name}…")
        slicer.app.processEvents()

        try:
            poly  = self._extract_polydata(kind, node_id, sid)
            color = self._get_color(kind, node_id, sid)
            poly  = self._process_mesh(poly)
            self._write_obj(poly, name, color)
            self._exported += 1
        except Exception as e:
            self._errors.append(f"{name}: {e}")
            slicer.app.processEvents()

        progress = int(100 * (self._exported + len(self._errors)) / self._total)
        self.progressBar.setValue(progress)
        qt.QTimer.singleShot(20, self._process_next)

    def _on_export_done(self):
        self.progressBar.setValue(100)
        msg = f"✓ Exported {self._exported}/{self._total} item(s) to:\n  {self._ctx['folder']}"
        if self._errors:
            msg += f"\n\n⚠ {len(self._errors)} error(s):"
            for err in self._errors:
                msg += f"\n  • {err}"
        self.statusLabel.setText(msg)
        self.exportBtn.setEnabled(True)
        self.refreshBtn.setEnabled(True)
        print(msg)

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  POLYDATA EXTRACTION  (segmentations & model nodes)                  ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _extract_polydata(self, kind, node_id, sid):
        node = slicer.mrmlScene.GetNodeByID(node_id)
        if node is None:
            raise RuntimeError("Node not found")

        if kind == 'segment':
            poly = self._extract_segment_world(node, sid)
            return poly

        if kind == 'model':
            poly = self._extract_model_world(node)
            return poly

        raise RuntimeError(f"Unknown item kind: {kind}")

    def _extract_segment_world(self, segNode, sid):
        """
        Extract a segment's closed surface in WORLD RAS coordinates.

        Strategy: export the segment to a temporary model node using Slicer's
        own logic, which correctly handles the segmentation's internal geometry
        (reference image origin, spacing, directions) AND any parent transforms.
        Then read the polydata from the model node and remove it.
        """
        # 1. Ensure closed surface exists
        segNode.CreateClosedSurfaceRepresentation()

        # 2. Create a temporary folder + model node
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(
            slicer.mrmlScene)
        exportFolderId = shNode.CreateFolderItem(
            shNode.GetSceneItemID(), "_temp_export")

        # 3. Use Slicer's segmentations logic to export — this bakes ALL transforms
        segLogic = slicer.modules.segmentations.logic()
        segIds = vtk.vtkStringArray()
        segIds.InsertNextValue(sid)                     # export only this segment
        ok = segLogic.ExportSegmentsToModels(
            segNode,                                    # segmentation node
            segIds,                                     # specific segment
            exportFolderId)                             # destination folder

        if not ok:
            # Fallback: try the direct extraction method
            print(f"  ⚠ ExportSegmentsToModels failed for '{segNode.GetName()}', using fallback")
            return self._extract_segment_fallback(segNode, sid)

        # 4. Find the model node matching our segment ID
        segment = segNode.GetSegmentation().GetSegment(sid)
        segName = segment.GetName()
        poly = None

        childIds = vtk.vtkIdList()
        shNode.GetItemChildren(exportFolderId, childIds, True)
        for i in range(childIds.GetNumberOfIds()):
            childItem = childIds.GetId(i)
            childNode = shNode.GetItemDataNode(childItem)
            if childNode and childNode.IsA("vtkMRMLModelNode"):
                if childNode.GetName() == segName or segName in childNode.GetName():
                    poly = vtk.vtkPolyData()
                    poly.DeepCopy(childNode.GetPolyData())
                    break

        # 5. Clean up temporary nodes
        childIds2 = vtk.vtkIdList()
        shNode.GetItemChildren(exportFolderId, childIds2, True)
        for i in range(childIds2.GetNumberOfIds()):
            childNode = shNode.GetItemDataNode(childIds2.GetId(i))
            if childNode:
                slicer.mrmlScene.RemoveNode(childNode)
        shNode.RemoveItem(exportFolderId)

        if poly is None or poly.GetNumberOfPoints() == 0:
            return self._extract_segment_fallback(segNode, sid)

        self._print_bounds("segment", segName, poly)
        return poly

    def _extract_segment_fallback(self, segNode, sid):
        """
        Fallback: direct closed surface extraction + manual transform baking.
        Used when ExportSegmentsToModels is unavailable or fails.
        """
        poly = vtk.vtkPolyData()
        ok = segNode.GetClosedSurfaceRepresentation(sid, poly)
        if not ok or poly.GetNumberOfPoints() == 0:
            raise RuntimeError("Empty closed surface representation")
        poly = self._apply_node_world_transform(segNode, poly)
        segName = segNode.GetSegmentation().GetSegment(sid).GetName()
        self._print_bounds("segment (fallback)", segName, poly)
        return poly

    def _extract_model_world(self, modelNode):
        """
        Extract a model node's polydata in WORLD RAS coordinates.
        """
        srcPoly = modelNode.GetPolyData()
        if srcPoly is None or srcPoly.GetNumberOfPoints() == 0:
            raise RuntimeError("Model has no polydata")
        poly = vtk.vtkPolyData()
        poly.DeepCopy(srcPoly)
        poly = self._apply_node_world_transform(modelNode, poly)
        self._print_bounds("model", modelNode.GetName(), poly)
        return poly

    def _apply_node_world_transform(self, node, poly):
        """
        Apply the FULL transform chain from a node's parent to world.
        Uses vtkGeneralTransform to handle linear, non-linear, and
        concatenated transform chains correctly.
        """
        parentTransform = node.GetParentTransformNode()
        if parentTransform is None:
            print(f"    [{node.GetName()}] no parent transform (already in world RAS)")
            return poly

        generalTransform = vtk.vtkGeneralTransform()
        slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(
            parentTransform, None, generalTransform)    # None = world

        tf = vtk.vtkTransformPolyDataFilter()
        tf.SetInputData(poly)
        tf.SetTransform(generalTransform)
        tf.Update()

        print(f"    [{node.GetName()}] parent transform '{parentTransform.GetName()}' "
              f"baked into polydata")
        return tf.GetOutput()

    @staticmethod
    def _print_bounds(kind, name, poly):
        """Print the bounding box in world RAS so user can verify alignment."""
        b = [0]*6
        poly.GetBounds(b)
        cx = (b[0]+b[1])/2
        cy = (b[2]+b[3])/2
        cz = (b[4]+b[5])/2
        print(f"  ✓ [{kind}] {name:20s}  "
              f"centre=({cx:+7.1f}, {cy:+7.1f}, {cz:+7.1f}) mm   "
              f"span=({b[1]-b[0]:.1f} × {b[3]-b[2]:.1f} × {b[5]-b[4]:.1f})")

    def _get_color(self, kind, node_id, sid):
        node = slicer.mrmlScene.GetNodeByID(node_id)
        if kind == 'segment':
            segment = node.GetSegmentation().GetSegment(sid)
            return list(segment.GetColor())
        dn = node.GetDisplayNode()
        return list(dn.GetColor()) if dn else [0.8, 0.8, 0.8]

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  MESH PROCESSING                                                     ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    def _process_mesh(self, poly):
        ctx = self._ctx

        # ─ Smoothing
        if ctx['smooth'] and ctx['smooth_iters'] > 0:
            sm = vtk.vtkWindowedSincPolyDataFilter()
            sm.SetInputData(poly)
            sm.SetNumberOfIterations(ctx['smooth_iters'])
            sm.SetPassBand(0.1)
            sm.NormalizeCoordinatesOn()
            sm.NonManifoldSmoothingOn()
            sm.FeatureEdgeSmoothingOff()
            sm.BoundarySmoothingOn()
            sm.Update()
            poly = sm.GetOutput()

        # ─ Decimation
        if ctx['decimate'] and ctx['decimate_target'] > 0.0:
            dec = vtk.vtkQuadricDecimation()
            dec.SetInputData(poly)
            dec.SetTargetReduction(ctx['decimate_target'])
            dec.Update()
            poly = dec.GetOutput()

        # ─ Coordinate system + scale
        #   RAS → LPS:   negate X (R→L) and Y (A→P) — this is two negations,
        #                so winding order is preserved (no normal flip needed)
        #   Scale:       uniform multiply
        t = vtk.vtkTransform()
        if ctx['coord_lps']:
            t.Scale(-1.0, -1.0, 1.0)
        if ctx['scale'] != 1.0:
            t.Scale(ctx['scale'], ctx['scale'], ctx['scale'])

        if ctx['coord_lps'] or ctx['scale'] != 1.0:
            f = vtk.vtkTransformPolyDataFilter()
            f.SetInputData(poly)
            f.SetTransform(t)
            f.Update()
            poly = f.GetOutput()

        # ─ Recompute normals (decimation invalidates them; transform may flip)
        nrm = vtk.vtkPolyDataNormals()
        nrm.SetInputData(poly)
        nrm.ComputePointNormalsOn()
        nrm.ComputeCellNormalsOff()
        nrm.SplittingOff()
        nrm.ConsistencyOn()
        nrm.AutoOrientNormalsOn()
        nrm.Update()
        poly = nrm.GetOutput()

        # ─ Double-sided: duplicate all triangles with reversed winding + normals
        #   so both faces render in Unity's Standard shader (which culls back faces).
        #   Uses vtkReverseSense to flip winding order and normals on a deep copy,
        #   then vtkAppendPolyData to merge original + reversed into one mesh.
        if ctx.get('double_sided', False):
            reversed_poly = vtk.vtkReverseSense()
            reversed_poly.SetInputData(poly)
            reversed_poly.ReverseCellsOn()
            reversed_poly.ReverseNormalsOn()
            reversed_poly.Update()

            append = vtk.vtkAppendPolyData()
            append.AddInputData(poly)
            append.AddInputData(reversed_poly.GetOutput())
            append.Update()

            # Clean: merge coincident points at shared edges to keep file compact
            clean = vtk.vtkCleanPolyData()
            clean.SetInputData(append.GetOutput())
            clean.PointMergingOn()
            clean.SetTolerance(0.0)    # exact merge only (no spatial fuzz)
            clean.Update()
            poly = clean.GetOutput()

        return poly

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  OBJ + MTL WRITER                                                    ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    @staticmethod
    def _safe_filename(name):
        out = name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
        return "".join(c for c in out if c.isalnum() or c in "._-") or "model"

    def _write_obj(self, poly, name, color):
        ctx = self._ctx
        prefix = ctx['prefix']
        if prefix and not prefix.endswith("_"):
            prefix = prefix + "_"

        safe     = self._safe_filename(name)
        base     = prefix + safe
        obj_path = os.path.join(ctx['folder'], f"{base}.obj")
        mtl_path = os.path.join(ctx['folder'], f"{base}.mtl")
        material = safe

        npoints = poly.GetNumberOfPoints()
        ncells  = poly.GetNumberOfCells()
        nrm_arr = poly.GetPointData().GetNormals()
        has_n   = nrm_arr is not None

        with open(obj_path, 'w', newline='\n') as f:
            units = "metres" if ctx['scale'] != 1.0 else "mm"
            f.write("# Exported by Slicer Unity Exporter\n")
            f.write(f"# Source       : {name}\n")
            f.write(f"# Coord system : {'LPS' if ctx['coord_lps'] else 'RAS'}\n")
            f.write(f"# Units        : {units}\n")
            f.write(f"# Vertices     : {npoints}\n")
            f.write(f"# Faces        : {ncells}\n")
            if ctx.get('double_sided', False):
                f.write(f"# Double-sided : yes (triangles duplicated with reversed normals)\n")

            if ctx['with_mtl']:
                f.write(f"mtllib {os.path.basename(mtl_path)}\n")

            # Vertices
            for i in range(npoints):
                p = poly.GetPoint(i)
                f.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")

            # Normals
            if has_n:
                n_count = nrm_arr.GetNumberOfTuples()
                for i in range(n_count):
                    n = nrm_arr.GetTuple3(i)
                    f.write(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")

            # Group + material + faces
            f.write(f"g {material}\n")
            if ctx['with_mtl']:
                f.write(f"usemtl {material}\n")

            for i in range(ncells):
                cell = poly.GetCell(i)
                npts = cell.GetNumberOfPoints()
                if npts < 3:
                    continue
                ids = [cell.GetPointId(j) + 1 for j in range(npts)]   # 1-indexed
                if has_n:
                    parts = [f"{vid}//{vid}" for vid in ids]
                else:
                    parts = [str(vid) for vid in ids]
                f.write("f " + " ".join(parts) + "\n")

        # MTL with material color (Unity reads this as the material's albedo)
        if ctx['with_mtl']:
            with open(mtl_path, 'w', newline='\n') as f:
                f.write(f"# Material for {name}\n")
                f.write(f"newmtl {material}\n")
                f.write(f"Ka {color[0]:.4f} {color[1]:.4f} {color[2]:.4f}\n")
                f.write(f"Kd {color[0]:.4f} {color[1]:.4f} {color[2]:.4f}\n")
                f.write(f"Ks 0.2000 0.2000 0.2000\n")
                f.write(f"Ns 20.0000\n")
                f.write(f"d 1.0000\n")
                f.write(f"illum 2\n")


# ──────────────────────────────────────────────────────────────────────────────
#  Show the dialog (singleton — closes any previous instance first)
# ──────────────────────────────────────────────────────────────────────────────

def show_export_dialog():
    if hasattr(slicer.modules, '_unity_export_dlg'):
        try:
            slicer.modules._unity_export_dlg.close()
            slicer.modules._unity_export_dlg.deleteLater()
        except Exception:
            pass
    slicer.modules._unity_export_dlg = ExportForUnityDialog()
    slicer.modules._unity_export_dlg.show()
    slicer.modules._unity_export_dlg.raise_()
    slicer.modules._unity_export_dlg.activateWindow()


show_export_dialog()
