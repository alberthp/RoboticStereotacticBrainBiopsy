/// FiducialLoader.cs
/// =================
/// Loads fiducial screw coordinates from a Slicer .fcsv file
/// and instantiates screw prefabs in the Unity scene.
///
/// .fcsv format (Slicer Markups CSV):
///   # Markups fiducial file version = 4.13
///   # CoordinateSystem = LPS
///   # columns = id,x,y,z,ow,ox,oy,oz,vis,sel,lock,label,desc,associatedNodeID
///   0,-17.344,58.255,50.503,0,0,0,1,1,1,0,F_1-1,,
///
/// Repository: RoboticStereotacticBrainBiopsy / 05_Unity_Core_Simulator

using UnityEngine;
using System.Collections.Generic;
using System.IO;

public class FiducialLoader : MonoBehaviour
{
    [Header("Configuration")]
    [Tooltip("Path to .fcsv file exported from 3D Slicer")]
    public string fcsvFilePath = "Assets/Data/ScrewFiducials_GroundTruth.fcsv";

    [Tooltip("Prefab to instantiate at each fiducial position")]
    public GameObject screwPrefab;

    [Tooltip("Parent transform for instantiated screws")]
    public Transform screwParent;

    [Header("Coordinate System")]
    [Tooltip("Slicer exports in LPS by default. Set true if file uses RAS.")]
    public bool fileIsRAS = false;

    // ── Public data ──────────────────────────────────────────────────────────
    public List<Vector3>  FiducialPositions { get; private set; } = new();
    public List<string>   FiducialLabels    { get; private set; } = new();

    // ── Lifecycle ────────────────────────────────────────────────────────────
    void Start()
    {
        LoadFiducials();
    }

    // ── Public API ───────────────────────────────────────────────────────────
    public void LoadFiducials()
    {
        FiducialPositions.Clear();
        FiducialLabels.Clear();

        if (!File.Exists(fcsvFilePath))
        {
            Debug.LogError($"[FiducialLoader] File not found: {fcsvFilePath}");
            return;
        }

        string[] lines = File.ReadAllLines(fcsvFilePath);
        foreach (string line in lines)
        {
            if (line.StartsWith("#") || string.IsNullOrWhiteSpace(line))
                continue;

            string[] parts = line.Split(',');
            if (parts.Length < 12) continue;

            if (!float.TryParse(parts[1], out float x)) continue;
            if (!float.TryParse(parts[2], out float y)) continue;
            if (!float.TryParse(parts[3], out float z)) continue;

            string label = parts[11].Trim();

            // Convert to Unity coordinates
            // Slicer LPS → Unity: negate x and y
            // Slicer RAS → Unity: negate x only
            Vector3 unityPos = fileIsRAS
                ? new Vector3(-x,  z,  y)   // RAS → Unity
                : new Vector3( x, -z, -y);  // LPS → Unity

            FiducialPositions.Add(unityPos);
            FiducialLabels.Add(label);
        }

        Debug.Log($"[FiducialLoader] Loaded {FiducialPositions.Count} fiducials.");
        SpawnScrews();
    }

    // ── Private ──────────────────────────────────────────────────────────────
    void SpawnScrews()
    {
        if (screwPrefab == null) return;

        Transform parent = screwParent != null ? screwParent : transform;

        for (int i = 0; i < FiducialPositions.Count; i++)
        {
            GameObject screw = Instantiate(screwPrefab, FiducialPositions[i],
                                           Quaternion.identity, parent);
            screw.name = FiducialLabels.Count > i
                         ? $"Screw_{FiducialLabels[i]}"
                         : $"Screw_{i}";

            // Add label in world space
            var label = new GameObject("Label");
            label.transform.SetParent(screw.transform);
            label.transform.localPosition = Vector3.up * 0.015f;
            var tm = label.AddComponent<TextMesh>();
            tm.text      = FiducialLabels.Count > i ? FiducialLabels[i] : i.ToString();
            tm.fontSize  = 14;
            tm.color     = Color.white;
            tm.alignment = TextAlignment.Center;
            tm.anchor    = TextAnchor.LowerCenter;
        }
    }
}
