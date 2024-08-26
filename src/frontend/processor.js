const SPEAKING_THRESHOLD = 0.02; // trigger threshold to start recording
const SILENCE_DURATION = 0.5; // seconds of silence before ending recording

class WorkletProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    
    // Configuration
    const processorOptions = options.processorOptions || {};
    this.SPEAKING_THRESHOLD = SPEAKING_THRESHOLD;
    this.SILENCE_DURATION = SILENCE_DURATION;

    // State
    this._buffer = [];
    this._isTalking = false;
    this._silenceCounter = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0][0];
    if (!input) return true; // Early return if no input

    const amplitude = this._calculateAmplitude(input);
    
    // every time user goes above threshold, we start recording
    // staying above that threshold maintains the recording state
    if (amplitude > this.SPEAKING_THRESHOLD) {
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
      if (this._buffer.length > 0) {
        this.port.postMessage({
          type: 'buffer',
          buffer: this._buffer
        });
        this._buffer = [];
      }
      this.port.postMessage({ type: 'silence' });
    }

    return true;
  }

  _calculateAmplitude(channelData) {
    return channelData.reduce((sum, value) => sum + Math.abs(value), 0) / channelData.length;
  }
}

registerProcessor("worklet-processor", WorkletProcessor);