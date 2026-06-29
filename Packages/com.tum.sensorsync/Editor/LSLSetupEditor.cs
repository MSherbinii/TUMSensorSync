using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class SensorSyncSetup
{
    [MenuItem("Tools/TUM Sensor Sync/Add to Scene")]
    static void AddToScene()
    {
        var scene = SceneManager.GetActiveScene();

        foreach (var root in scene.GetRootGameObjects())
            if (root.GetComponentInChildren<LSLManager>() != null)
            {
                Debug.Log("[SensorSync] Already present in scene.");
                return;
            }

        var go = new GameObject("SensorSync");
        go.AddComponent<LSLManager>();
        go.AddComponent<LSLEventBridge>();
        SceneManager.MoveGameObjectToScene(go, scene);
        EditorSceneManager.MarkSceneDirty(scene);
        Selection.activeGameObject = go;
        Debug.Log("[SensorSync] Added LSLManager + LSLEventBridge to scene.");
    }

    [MenuItem("Tools/TUM Sensor Sync/Validate")]
    static void Validate()
    {
        bool lsl4unity = System.IO.Directory.Exists("Packages/com.labstreaminglayer.lsl4unity");
        bool nativeLib = System.IO.File.Exists("Packages/com.tum.sensorsync/Plugins/Android/libs/arm64-v8a/liblsl.so") ||
                         System.IO.File.Exists("Packages/com.labstreaminglayer.lsl4unity/Plugins/LSL/Android/arm64-v8a/liblsl.so");

        string msg = $"[SensorSync] Validation:\n" +
                     $"  LSL4Unity: {(lsl4unity ? "OK" : "MISSING")}\n" +
                     $"  Android ARM64 lib: {(nativeLib ? "OK" : "MISSING")}\n" +
                     $"  Build target: {EditorUserBuildSettings.activeBuildTarget}";

        if (lsl4unity && nativeLib) Debug.Log(msg);
        else Debug.LogWarning(msg);
    }
}
