using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Events;

[AddComponentMenu("TUM/Sensor Sync/LSL Event Bridge")]
public class LSLEventBridge : MonoBehaviour
{
    [Serializable]
    public class MarkerBinding
    {
        public string markerName;
        public UnityEvent onFire;
    }

    [SerializeField] private List<MarkerBinding> _bindings = new List<MarkerBinding>();
    [SerializeField] private bool _syncFlashOnLoad = true;
    [SerializeField] private bool _syncFlashOnScenarioStart;

    private float _lastFrameTime;
    private int _buttonPressSeq;

    void Start()
    {
        if (_syncFlashOnLoad)
            LSLManager.Instance?.FireSyncFlash();

        foreach (var b in _bindings)
        {
            var name = b.markerName;
            b.onFire.AddListener(() => LSLManager.Instance?.SendMarker(name));
        }
    }

    void Update()
    {
        _lastFrameTime = Time.realtimeSinceStartup;
    }

    public void FireMarker(string markerName)
    {
        LSLManager.Instance?.SendMarker(markerName);
    }

    public void FireConfiguredMarker(int index)
    {
        if (index >= 0 && index < _bindings.Count)
            LSLManager.Instance?.SendMarker(_bindings[index].markerName);
    }

    public void FireSyncFlash()
    {
        LSLManager.Instance?.FireSyncFlash();
    }

    public void FireSyncFlashOnScenarioStart()
    {
        if (_syncFlashOnScenarioStart)
            LSLManager.Instance?.FireSyncFlash();
    }

    public ButtonPressEvent FireButtonPressMarker()
    {
        _buttonPressSeq++;
        float now = Time.realtimeSinceStartup;
        int frame = Time.frameCount;
        float dt = Time.deltaTime;
        float sinceLastFrame = now - _lastFrameTime;

        string marker = $"ButtonPress:seq={_buttonPressSeq}:unityMs={now:F6}:frame={frame}:dt={dt:F3}:sinceLastFrame={sinceLastFrame:F3}";
        LSLManager.Instance?.SendMarker(marker);

        return new ButtonPressEvent
        {
            sequenceNumber = _buttonPressSeq,
            unityTimestamp = now.ToString("F6"),
            frameTimeSinceStart = now,
            frameCount = frame,
            deltaTime = dt,
            timeSinceLastFrame = sinceLastFrame,
            lslMarkerFired = marker
        };
    }
}

[Serializable]
public class ButtonPressEvent
{
    public int sequenceNumber;
    public string unityTimestamp;
    public float frameTimeSinceStart;
    public int frameCount;
    public float deltaTime;
    public float timeSinceLastFrame;
    public string lslMarkerFired;
}
