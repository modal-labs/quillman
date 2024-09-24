class RecorderNode extends AudioWorkletNode {
  constructor(context, onAmplitude) {
    super(context, "worklet-processor");
    
    this.port.onmessage = (event) => {
      switch(event.data.type) {
        // case 'buffer': // buffers are sent on brief pauses
        //   onBufferReceived(event.data.buffer);
        //   break;
        case 'amplitude':
          onAmplitude(event.data.value);
      }
    };
  }

  // mute() {
  //   this.port.postMessage({ type: 'mute' });
  // }

  // unmute() {
  //   this.port.postMessage({ type: 'unmute' });
  // }
}

export default RecorderNode;