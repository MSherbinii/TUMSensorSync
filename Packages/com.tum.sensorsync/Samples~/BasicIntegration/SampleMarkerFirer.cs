using UnityEngine;

public class SampleMarkerFirer : MonoBehaviour
{
    void Start()
    {
        LSLManager.Instance?.SendMarker("SceneLoaded:" + gameObject.scene.name);
    }

    public void OnUserAction(string action)
    {
        LSLManager.Instance?.SendMarker($"UserAction:{action}");
    }
}
