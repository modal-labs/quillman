class RecorderNode extends AudioWorkletNode {
  constructor(context, onBufferReceived, onSilence, onTalking, options = {}) {
    super(context, "worklet-processor");
    
    this.port.onmessage = (event) => {
      switch(event.data.type) {
        case 'buffer':
          onBufferReceived(event.data.buffer);
          break;
        case 'silence':
          onSilence();
          break;
        case 'talking':
          onTalking();
          break;
      }
    };
  }
}

export default RecorderNode;