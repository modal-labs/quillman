class RecorderNode extends AudioWorkletNode {
  constructor(context, onSegmentRecv, onSilence, onTalking) {
    super(context, "worklet-processor");
    this.port.onmessage = (event) => {
      if (event.data.type === "segment") {
        onSegmentRecv(event.data.buffer);
      } else if (event.data.type === "silence") {
        onSilence();
      } else if (event.data.type === "talking") {
        onTalking();
      }
    };
  }

  stop() {
    this.port.postMessage({ type: "stop" });
  }

  start() {
    this.port.postMessage({ type: "start" });
  }
}

export default RecorderNode;
