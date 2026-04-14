# 05 — Unity Core Simulator

Main surgical simulation: registration, planning, and robotic guidance.

## Scene Components
- Skull mesh (from module 02)
- Brain mesh (from module 02)
- Tumour mesh + centroid marker (from module 02)
- Virtual probe (tracked via OpenIGTLink or mouse input)
- Fiducial marker spheres (from module 03 .fcsv)
- Robotic arm model (Franka Emika)
- Insertion trajectory line renderer

## Key Scripts
- `FiducialLoader.cs` — parses .fcsv and instantiates screw prefabs
- `SVDRegistration.cs` — computes rigid transform from two point clouds
- `RegistrationManager.cs` — manages the registration workflow
- `TrajectoryPlanner.cs` — computes optimal insertion path to tumour
- `DrillSimulator.cs` — simulates burr hole creation

## Registration Algorithm
Point-to-point SVD registration (Arun et al., 1987):
1. Compute centroids of both point clouds
2. Centre both clouds
3. Compute cross-covariance matrix H
4. SVD decompose: H = U Σ Vᵀ
5. Rotation: R = V Uᵀ
6. Translation: t = centroid_physical - R * centroid_virtual

## Coordinate Conversion (Slicer RAS → Unity)
```csharp
Vector3 SlicerToUnity(float R, float A, float S) {
    return new Vector3(-R, S, A);
}
```
