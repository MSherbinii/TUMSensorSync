using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using LSL;

[AddComponentMenu("TUM/Sensor Sync/LSL Manager")]
public class LSLManager : MonoBehaviour
{
    public static LSLManager Instance { get; private set; }

    [SerializeField]
    [Tooltip("LSL outlet name. Must be unique per concurrent Unity app on the network. " +
             "Must match marker_stream_name in orchestrator/config.json.")]
    private string _markerStreamName = "UnityMarkers";

    public string MarkerStreamName => _markerStreamName;

    private StreamOutlet _markerOutlet;
    private readonly string[] _sample = new string[1];

    private GameObject _flashOverlay;
    private Image _flashImage;
    private int _flashId;

    void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(gameObject); return; }
        Instance = this;
        DontDestroyOnLoad(gameObject);

        try
        {
            var info = new StreamInfo(
                _markerStreamName, "Markers", 1,
                LSL.LSL.IRREGULAR_RATE,
                channel_format_t.cf_string,
                _markerStreamName + "_" + SystemInfo.deviceUniqueIdentifier
            );
            _markerOutlet = new StreamOutlet(info);
        }
        catch (System.Exception e)
        {
            Debug.LogError($"[SensorSync] LSL outlet failed: {e.Message}");
        }

        CreateFlashOverlay();
    }

    public void SendMarker(string marker)
    {
        if (_markerOutlet == null) return;
        _sample[0] = marker;
        _markerOutlet.push_sample(_sample);
    }

    public void FireSyncFlash()
    {
        StartCoroutine(SyncFlashRoutine());
    }

    private IEnumerator SyncFlashRoutine()
    {
        int id = ++_flashId;
        float t0 = Time.realtimeSinceStartup;

        SendMarker($"SyncFlashRequest:id={id}");

        _flashImage.color = Color.white;
        _flashOverlay.SetActive(true);
        SendMarker($"SyncFlashStateSet:id={id}");
        SendMarker($"SyncFlash:id={id}");

        yield return new WaitForEndOfFrame();
        float ms = (Time.realtimeSinceStartup - t0) * 1000f;
        SendMarker($"SyncFlashEndOfFrame:id={id}:unityMs={ms:F1}");

        _flashImage.color = new Color(1, 1, 1, 0.66f); yield return null;
        _flashImage.color = new Color(1, 1, 1, 0.33f); yield return null;
        _flashOverlay.SetActive(false);

        FrameTimingManager.CaptureFrameTimings();
        StartCoroutine(EmitFrameTiming(id));
    }

    private IEnumerator EmitFrameTiming(int id)
    {
        for (int i = 0; i < 6; i++) yield return null;

        FrameTiming[] ft = new FrameTiming[1];
        uint count = FrameTimingManager.GetLatestTimings(1, ft);
        if (count > 0)
            SendMarker($"SyncFlashFrameTiming:id={id}:cpuMs={ft[0].cpuFrameTime:F1}:gpuMs={ft[0].gpuFrameTime:F1}");
        else
            SendMarker($"SyncFlashFrameTiming:id={id}:cpuMs=NA:gpuMs=NA");
    }

    private void CreateFlashOverlay()
    {
        _flashOverlay = new GameObject("SyncFlashOverlay");
        DontDestroyOnLoad(_flashOverlay);
        _flashOverlay.SetActive(false);

        var canvas = _flashOverlay.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvas.sortingOrder = 9999;

        var img = new GameObject("Fill");
        img.transform.SetParent(_flashOverlay.transform, false);
        _flashImage = img.AddComponent<Image>();
        _flashImage.color = Color.white;

        var rect = img.GetComponent<RectTransform>();
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = Vector2.zero;
        rect.offsetMax = Vector2.zero;
    }

    void OnDestroy()
    {
        _markerOutlet?.Close();
    }
}
