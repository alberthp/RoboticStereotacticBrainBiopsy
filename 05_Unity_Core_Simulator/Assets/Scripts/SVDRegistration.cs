/// SVDRegistration.cs
/// ==================
/// Point-to-point rigid registration using Singular Value Decomposition.
/// Computes the rotation R and translation t that best aligns a set of
/// virtual fiducial points to their corresponding physical measurements.
///
/// Algorithm: Arun et al., "Least-Squares Fitting of Two 3-D Point Sets",
/// IEEE TPAMI, 1987.
///
/// Repository: RoboticStereotacticBrainBiopsy / 05_Unity_Core_Simulator

using UnityEngine;
using System.Collections.Generic;

public class SVDRegistration : MonoBehaviour
{
    // ── Public API ──────────────────────────────────────────────────────────

    /// <summary>
    /// Compute rigid registration from virtualPoints to physicalPoints.
    /// Returns the 4x4 transform matrix (physical = R * virtual + t).
    /// </summary>
    public static Matrix4x4 Register(
        List<Vector3> virtualPoints,
        List<Vector3> physicalPoints)
    {
        if (virtualPoints.Count != physicalPoints.Count || virtualPoints.Count < 3)
        {
            Debug.LogError("Need at least 3 corresponding point pairs.");
            return Matrix4x4.identity;
        }

        int n = virtualPoints.Count;

        // Step 1 — Compute centroids
        Vector3 centroidV = ComputeCentroid(virtualPoints);
        Vector3 centroidP = ComputeCentroid(physicalPoints);

        // Step 2 — Centre both point clouds
        float[,] A = new float[3, n];
        float[,] B = new float[3, n];
        for (int i = 0; i < n; i++)
        {
            Vector3 a = virtualPoints[i]  - centroidV;
            Vector3 b = physicalPoints[i] - centroidP;
            A[0,i] = a.x; A[1,i] = a.y; A[2,i] = a.z;
            B[0,i] = b.x; B[1,i] = b.y; B[2,i] = b.z;
        }

        // Step 3 — Cross-covariance matrix H = A * Bᵀ
        float[,] H = MatMul(A, Transpose(B));

        // Step 4 — SVD decomposition of H
        float[,] U, S, Vt;
        SVD3x3(H, out U, out S, out Vt);

        // Step 5 — Rotation R = V * Uᵀ
        float[,] R = MatMul(Transpose(Vt), Transpose(U));

        // Handle reflection case (det(R) should be +1)
        if (Determinant3x3(R) < 0)
        {
            float[,] V = Transpose(Vt);
            V[0,2] = -V[0,2];
            V[1,2] = -V[1,2];
            V[2,2] = -V[2,2];
            R = MatMul(V, Transpose(U));
        }

        // Step 6 — Translation t = centroidP - R * centroidV
        Vector3 rCentroidV = ApplyRotation(R, centroidV);
        Vector3 t = centroidP - rCentroidV;

        // Step 7 — Build 4x4 matrix
        Matrix4x4 result = Matrix4x4.identity;
        result.m00 = R[0,0]; result.m01 = R[0,1]; result.m02 = R[0,2]; result.m03 = t.x;
        result.m10 = R[1,0]; result.m11 = R[1,1]; result.m12 = R[1,2]; result.m13 = t.y;
        result.m20 = R[2,0]; result.m21 = R[2,1]; result.m22 = R[2,2]; result.m23 = t.z;

        return result;
    }

    /// <summary>
    /// Compute RMS Fiducial Registration Error after registration.
    /// </summary>
    public static float ComputeFRE(
        List<Vector3> virtualPoints,
        List<Vector3> physicalPoints,
        Matrix4x4 transform)
    {
        float sumSq = 0f;
        for (int i = 0; i < virtualPoints.Count; i++)
        {
            Vector3 transformed = transform.MultiplyPoint3x4(virtualPoints[i]);
            sumSq += (transformed - physicalPoints[i]).sqrMagnitude;
        }
        return Mathf.Sqrt(sumSq / virtualPoints.Count);
    }

    /// <summary>
    /// Convert Slicer RAS coordinates to Unity world coordinates.
    /// Slicer: Right-Anterior-Superior (RAS)
    /// Unity:  Left-handed Y-up
    /// </summary>
    public static Vector3 SlicerRASToUnity(float R, float A, float S)
    {
        return new Vector3(-R, S, A);
    }

    // ── Private helpers ─────────────────────────────────────────────────────

    static Vector3 ComputeCentroid(List<Vector3> pts)
    {
        Vector3 sum = Vector3.zero;
        foreach (var p in pts) sum += p;
        return sum / pts.Count;
    }

    static float[,] Transpose(float[,] m)
    {
        int r = m.GetLength(0), c = m.GetLength(1);
        float[,] t = new float[c, r];
        for (int i = 0; i < r; i++)
            for (int j = 0; j < c; j++)
                t[j, i] = m[i, j];
        return t;
    }

    static float[,] MatMul(float[,] A, float[,] B)
    {
        int m = A.GetLength(0), k = A.GetLength(1), n = B.GetLength(1);
        float[,] C = new float[m, n];
        for (int i = 0; i < m; i++)
            for (int j = 0; j < n; j++)
                for (int p = 0; p < k; p++)
                    C[i,j] += A[i,p] * B[p,j];
        return C;
    }

    static float Determinant3x3(float[,] m)
    {
        return m[0,0] * (m[1,1]*m[2,2] - m[1,2]*m[2,1])
             - m[0,1] * (m[1,0]*m[2,2] - m[1,2]*m[2,0])
             + m[0,2] * (m[1,0]*m[2,1] - m[1,1]*m[2,0]);
    }

    static Vector3 ApplyRotation(float[,] R, Vector3 v)
    {
        return new Vector3(
            R[0,0]*v.x + R[0,1]*v.y + R[0,2]*v.z,
            R[1,0]*v.x + R[1,1]*v.y + R[1,2]*v.z,
            R[2,0]*v.x + R[2,1]*v.y + R[2,2]*v.z);
    }

    /// <summary>
    /// Jacobi SVD for 3x3 matrices.
    /// Produces U, S (diagonal values), Vt such that M = U * diag(S) * Vt
    /// </summary>
    static void SVD3x3(float[,] M,
        out float[,] U, out float[,] S, out float[,] Vt)
    {
        // Use Unity's built-in via intermediate Quaternion decomposition
        // For production use, replace with Math.NET Numerics SVD
        // This is a simplified Jacobi iteration for 3x3
        int n = 3;
        float[,] A = (float[,])M.Clone();
        U  = Identity3(); 
        Vt = Identity3();
        S  = new float[3, 3];

        for (int sweep = 0; sweep < 30; sweep++)
        {
            for (int p = 0; p < n - 1; p++)
            {
                for (int q = p + 1; q < n; q++)
                {
                    float apq = A[p,q];
                    float app = A[p,p];
                    float aqq = A[q,q];
                    if (Mathf.Abs(apq) < 1e-9f) continue;

                    float tau   = (aqq - app) / (2f * apq);
                    float t     = (tau >= 0)
                                  ? 1f / ( tau + Mathf.Sqrt(1 + tau*tau))
                                  : 1f / ( tau - Mathf.Sqrt(1 + tau*tau));
                    float c     = 1f / Mathf.Sqrt(1 + t*t);
                    float s     = t * c;

                    // Update A
                    A[p,p] = app - t * apq;
                    A[q,q] = aqq + t * apq;
                    A[p,q] = 0f;
                    A[q,p] = 0f;
                    for (int r = 0; r < n; r++)
                    {
                        if (r != p && r != q)
                        {
                            float arp = A[r,p], arq = A[r,q];
                            A[r,p] = A[p,r] = c*arp - s*arq;
                            A[r,q] = A[q,r] = s*arp + c*arq;
                        }
                    }

                    // Accumulate rotations in V
                    for (int r = 0; r < n; r++)
                    {
                        float vrp = Vt[r,p], vrq = Vt[r,q];
                        Vt[r,p] = c*vrp - s*vrq;
                        Vt[r,q] = s*vrp + c*vrq;
                    }
                }
            }
        }

        // Singular values on diagonal of A
        for (int i = 0; i < n; i++)
            S[i,i] = A[i,i];

        // U = M * V * S^-1
        float[,] V = Transpose(Vt);
        float[,] MV = MatMul(M, V);
        U = new float[3,3];
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++)
                U[i,j] = (Mathf.Abs(S[j,j]) > 1e-9f)
                          ? MV[i,j] / S[j,j]
                          : 0f;
        Vt = Transpose(V);
    }

    static float[,] Identity3()
    {
        return new float[3,3] { {1,0,0}, {0,1,0}, {0,0,1} };
    }
}
