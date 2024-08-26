class WorkletProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    
    // Configuration
    const processorOptions = options.processorOptions || {};
    this.SILENCE_THRESHOLD = 0.01;
    this.SILENCE_DURATION = 1; // seconds of silence before we send a buffer

    // State
    this._buffer = [];
    this._isTalking = false;
    this._silenceCounter = 0;

    // The sampleRate is globally available in AudioWorkletProcessor
    console.log(`Initialized with sample rate: ${sampleRate}`);
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0][0];
    if (!input) return true; // Early return if no input

    const amplitude = this._calculateAmplitude(input);
    
    // every time user goes above threshold, we start recording
    // staying above that threshold maintains the recording state
    if (amplitude > this.SILENCE_THRESHOLD) {
      if (!this._isTalking) {
        // this means there was a state transition so send signal to main thread
        this.port.postMessage({ type: 'talking' });
      }
      this._silenceCounter = 0;
      this._isTalking = true;
    } else {
      // increment silence counter
      this._silenceCounter += input.length / sampleRate;
    }

    if (this._isTalking && this._silenceCounter <= this.SILENCE_DURATION) {
      // if we're talking and we're not at the end of the silence duration, add to buffer
      this._buffer.push(...input);
    }

    if (this._isTalking && this._silenceCounter >= this.SILENCE_DURATION) {
      // if we're talking and we're at the end of the silence duration, send buffer
      this._isTalking = false;
      this._sendBuffer();
      this.port.postMessage({ type: 'silence' });
    }

    return true;
  }

  _calculateAmplitude(channelData) {
    return channelData.reduce((sum, value) => sum + Math.abs(value), 0) / channelData.length;
  }

  _sendBuffer() {
    if (this._buffer.length > 0) {
      this.port.postMessage({
        type: 'buffer',
        buffer: this._buffer
      });
      this._buffer = [];
    }
  }
}

registerProcessor("worklet-processor", WorkletProcessor);