const PAUSE_DURATION = 0.5; // seconds of silence before sending a chunk
const END_DURATION = 3; // seconds of silence before ending recording

class WorkletProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    
    // Configuration
    const processorOptions = options.processorOptions || {};
    this.PAUSE_DURATION = PAUSE_DURATION;
    this.END_DURATION = END_DURATION;
    this.isMuted = true;

    this.talkingThreshold = 0.1; // initial value

    // State
    this._buffer = [];
    this._isTalking = false;
    this._isRecordingSession = false;
    this._silenceCounter = 0;

    // Add message event listener
    this.port.onmessage = this.handleMessage.bind(this);
  }

  handleMessage(event) {
    if (event.data.type === 'updateThreshold') {
      this.talkingThreshold = event.data.value;
    }
    if (event.data.type === 'mute') {
      this.isMuted = true;
    }
    if (event.data.type === 'unmute') {
      this.isMuted = false;
    }
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0][0];
    if (!input) return true; // Early return if no input

    const amplitude = this._calculateAmplitude(input);
    this.port.postMessage({ type: 'amplitude', value: amplitude });

    if (this.isMuted) return true;
    
    // every time user goes above threshold, we start recording
    // staying above that threshold maintains the recording state
    if (amplitude > this.talkingThreshold) {
      if (!this._isTalking) {
        // this means there was a state transition so send signal to main thread
        this.port.postMessage({ type: 'talking' });
      }
      this._silenceCounter = 0;
      this._isTalking = true;
      this._isRecordingSession = true;
    } else {
      // increment silence counter
      this._silenceCounter += input.length / sampleRate;
    }

    // add to buffer if recording session
    if (this._isRecordingSession) {
      this._buffer.push(...input);
    }

    // send accumulated buffer if user pauses
    if (this._isTalking && this._silenceCounter >= this.PAUSE_DURATION) {
      this._isTalking = false;
      if (this._buffer.length > 0) {
        this.port.postMessage({
          type: 'buffer',
          buffer: this._buffer
        });
        this._buffer = [];
      }
    }

    // end recording session if silence exceeds end duration. This triggers the bot to generate a response
    if (this._isRecordingSession && !this._isTalking && this._silenceCounter >= this.END_DURATION) {
      this.port.postMessage({ type: 'silence' });
      this._isRecordingSession = false;
      this._buffer = [];
    }
    
    return true;
  }

  _calculateAmplitude(channelData) {
    return channelData.reduce((sum, value) => sum + Math.abs(value), 0) / channelData.length;
  }
}

registerProcessor("worklet-processor", WorkletProcessor);