class RecorderNode extends AudioWorkletNode {
  constructor(context, onBufferReceived, onTalking, onSilence, onAmplitude, options = {}) {
    super(context, "worklet-processor");
    
    this.port.onmessage = (event) => {
      switch(event.data.type) {
        case 'buffer': // buffers are sent on brief pauses
          onBufferReceived(event.data.buffer);
          break;
        case 'talking': // on user talking
          onTalking();
          break;
        case 'silence': // on prolonged silence
          onSilence();
          break;
        case 'amplitude':
          onAmplitude(event.data.value);
          break;
      }
    };
  }

  updateThreshold(value) {
    this.port.postMessage({ type: 'updateThreshold', value });
  }

  mute() {
    this.port.postMessage({ type: 'mute' });
  }

  unmute() {
    this.port.postMessage({ type: 'unmute' });
  }
}

export default RecorderNode;