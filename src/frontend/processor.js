const SILENCE_THRESHOLD = 0.015;
const SAMPLE_RATE = 48000;
const CHANNEL_DATA_LENGTH = 128;
const MAX_SEGMENT_LENGTH = 10; // seconds
const MIN_TALKING_TIME = 2; // seconds
const AMPLITUDE_WINDOW = 0.5; // seconds

class WorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._bufferSize = MAX_SEGMENT_LENGTH * SAMPLE_RATE;
    this._buffer = new Float32Array(this._bufferSize);
    this._writeIndex = 0;

    this._amplitudeHistorySize = Math.floor(
      (AMPLITUDE_WINDOW * SAMPLE_RATE) / CHANNEL_DATA_LENGTH
    );
    this._lastAmplitudes = new Array();
    this._amplitudeSum = 0;
    this._stopped = false;
    this._lastEventState = null;
    this._lastEventTime = new Date();
    this._talkingTime = 0;

    this.port.onmessage = (event) => {
      if (event.data.type === "stop") {
        this._stopped = true;
        if (this._lastEventState !== "silence") {
          this.port.postMessage({ type: "silence" });
        }
        this._maybeSendSegment();
      } else if (event.data.type === "start") {
        this._talkingTime = 0;
        this._writeIndex = 0;
        this._stopped = false;
        this._lastEventState = null;
        this._lastEventTime = new Date();
      }
    };
  }

  _maybeSendSegment() {
    if (this._talkingTime > MIN_TALKING_TIME) {
      console.log("Sending segment");
      this.port.postMessage({ type: "segment", buffer: this._buffer });
    }
  }

  process(inputs, outputs, parameters) {
    if (this._stopped) {
      return true;
    }
    const channelData = inputs[0][0];

    const amplitude =
      channelData.reduce((s, v) => s + Math.abs(v), 0) / channelData.length;

    if (this._lastAmplitudes.length >= this._amplitudeHistorySize) {
      const front = this._lastAmplitudes.shift();
      this._amplitudeSum -= front;
    }

    this._lastAmplitudes.push(amplitude);
    this._amplitudeSum += amplitude;

    const averageAmplitude = this._amplitudeSum / this._lastAmplitudes.length;

    this._buffer.set(channelData, this._writeIndex);
    this._writeIndex += channelData.length;
    const remainingBufferSize = this._bufferSize - this._writeIndex;

    if (averageAmplitude > SILENCE_THRESHOLD) {
      if (this._lastEventState !== "talking") {
        this._lastEventState = "talking";
        this.port.postMessage({ type: "talking" });
      }
    } else {
      if (this._lastEventState !== "silence") {
        this._talkingTime += (new Date() - this._lastEventTime) / 1000;
        this._lastEventState = "silence";
        this._lastEventTime = new Date();
        this.port.postMessage({ type: "silence" });
      }
    }

    // If we have a silence or are running out of buffer space, send everything
    // we have if it's long enough, and then reset the buffer.
    if (
      (averageAmplitude <= SILENCE_THRESHOLD &&
        this._talkingTime > MIN_TALKING_TIME) ||
      remainingBufferSize < channelData.length
    ) {
      this._maybeSendSegment();
      this._buffer = new Float32Array(this._bufferSize);
      this._writeIndex = 0;
      this._talkingTime = 0;
      this._lastEventTime = new Date();
    }

    return true;
  }
}

registerProcessor("worklet-processor", WorkletProcessor);
