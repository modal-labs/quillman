const { useRef, useEffect, useState } = React;

const baseURL = "" // points to whatever is serving this app (eg your -dev.modal.run for modal serve, or .modal.run for modal deploy)

const getBaseURL = () => {
  return "wss://erik-dunteman--quillman-moshi-web-dev.modal.run/ws"; // temporary erik!
  // erik todo for tomorrow, look at moshi repo frontend! the playback's gotta be in there.

  // use current web app server domain to construct the url for the moshi app
  const currentURL = new URL(window.location.href);
  let hostname = currentURL.hostname;
  hostname = hostname.replace('-web', '-moshi-web');
  const wsProtocol = currentURL.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${hostname}/ws`; 
}

const App = () => {
  const socketRef = useRef(null);
  const [recorder, setRecorder] = useState(null);
  const [completedSentences, setCompletedSentences] = useState([]);
  const [pendingSentence, setPendingSentence] = useState('');
  const [warmupComplete, setWarmupComplete] = useState(false);
  const [amplitude, setAmplitude] = useState(0);
  const [audioContext] = useState(() => new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 }));
  
  const sourceNodeRef = useRef(null);
  const scheduledEndTimeRef = useRef(0);
  const decoderRef = useRef(null);

  const scheduleAudioPlayback = (newAudioData) => {
    const sampleRate = audioContext.sampleRate;
    const numberOfChannels = 1;
    const nowTime = audioContext.currentTime;
  
    // Create a new buffer for the incoming audio data
    const newBuffer = audioContext.createBuffer(numberOfChannels, newAudioData.length, sampleRate);
    newBuffer.copyToChannel(newAudioData, 0);
  
    // Create a new source node for this piece of audio
    const sourceNode = audioContext.createBufferSource();
    sourceNode.buffer = newBuffer;
    sourceNode.connect(audioContext.destination);
  
    // Schedule the new audio to play immediately after any currently playing audio
    const startTime = Math.max(scheduledEndTimeRef.current, nowTime);
    sourceNode.start(startTime);
  
    // Update the scheduled end time
    scheduledEndTimeRef.current = startTime + newBuffer.duration;
  
    // Clean up the previous source node if it exists and has ended
    if (sourceNodeRef.current && sourceNodeRef.current.buffer) {
      const currentEndTime = sourceNodeRef.current.startTime + sourceNodeRef.current.buffer.duration;
      if (currentEndTime <= nowTime) {
        sourceNodeRef.current.disconnect();
      }
    }
  
    // Update the current source node reference
    sourceNodeRef.current = sourceNode;
  };
  
  // start recording
  const startRecording = async () => {
    // used to get permission to use microphone
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    const recorder = new Recorder({
      encoderPath: "https://cdn.jsdelivr.net/npm/opus-recorder@latest/dist/encoderWorker.min.js",
      streamPages: true,
      encoderApplication: 2049,
      encoderFrameSize: 80, // milliseconds, equal to 1920 samples at 24000 Hz
      encoderSampleRate: 24000,  // 24000 to match model's sample rate
      maxFramesPerPage: 1,
      numberOfChannels: 1,
    });

    recorder.ondataavailable = async (arrayBuffer) => {
      if (socketRef.current) {
        if (socketRef.current.readyState !== WebSocket.OPEN) {
          console.log("Socket not open, dropping audio");
          return;
        }
        await socketRef.current.send(arrayBuffer);
      }
    };

    recorder.start().then(() => {
      console.log("Recording started");
      setRecorder(recorder);
    });

    // create a MediaRecorder object for capturing PCM (calculating amplitude)
    const analyzer = audioContext.createAnalyser();
    analyzer.fftSize = 256;
    const sourceNode = audioContext.createMediaStreamSource(stream);
    sourceNode.connect(analyzer);
    const mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = async (event) => {
      const dataArray = new Uint8Array(analyzer.frequencyBinCount);
      analyzer.getByteFrequencyData(dataArray);
      const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length;
      setAmplitude(average);
    };
    mediaRecorder.start(10);
  };

  // prep context and decoder for audio playback
  useEffect(() => {
    const initializeDecoder = async () => {
      const decoder = new window["ogg-opus-decoder"].OggOpusDecoder();
      await decoder.ready;
      decoderRef.current = decoder;
      console.log("Ogg Opus decoder initialized");
    };
  
    initializeDecoder();
  
    return () => {
      if (decoderRef.current) {
        decoderRef.current.free();
      }
    };
  }, []);


  // open websocket connection
  useEffect(() => {
    const endpoint = getBaseURL();
    console.log("Connecting to", endpoint);
    const socket = new WebSocket(endpoint);
    socketRef.current = socket;

    socket.onopen = () => {
      console.log("WebSocket connection opened");
      startRecording();
      setWarmupComplete(true);
    };

    socket.onmessage = async (event) => {
      // data is a blob, convert to array buffer
      const arrayBuffer = await event.data.arrayBuffer();
      const view = new Uint8Array(arrayBuffer);
      const tag = view[0];
      const payload = arrayBuffer.slice(1);
      if (tag === 1) {
        // audio data
        const { channelData, samplesDecoded, sampleRate } = await decoderRef.current.decode(new Uint8Array(payload));
        if (samplesDecoded > 0) {
          scheduleAudioPlayback(channelData[0]);
        }
      }
      if (tag === 2) {
        // text data
        const decoder = new TextDecoder();
        const text = decoder.decode(payload);

        setPendingSentence(prevPending => {
          const updatedPending = prevPending + text;
          if (updatedPending.endsWith('.') || updatedPending.endsWith('!') || updatedPending.endsWith('?')) {
            setCompletedSentences(prevCompleted => [...prevCompleted, updatedPending]);
            return '';
          }
          return updatedPending;
        });
      }
    };

    socket.onclose = () => {
      console.log("WebSocket connection closed");
    };

    return () => {
      socket.close();
    };
  }, []);

  return (
    <div className="bg-gray-900 text-white min-h-screen flex items-center justify-center p-4">
      <div className="bg-gray-800 rounded-lg shadow-lg w-full max-w-xl p-6">
        <div className="flex">
          <div className="w-5/6 overflow-y-auto max-h-64">
            <TextOutput warmupComplete={warmupComplete} completedSentences={completedSentences} pendingSentence={pendingSentence} />
          </div>
          <div className="w-1/6 ml-4 px-4">
            <AudioControl recorder={recorder} amplitude={amplitude} />
          </div>
        </div>
      </div>
    </div>
  );
}

const AudioControl = ({ recorder, amplitude }) => {
  const [muted, setMuted] = useState(true);

  const toggleMute = () => {
    if (!recorder) {
      return;
    }
    setMuted(!muted);
    recorder.setRecordingGain(muted ? 1 : 0);
  };

  // unmute automatically once the recorder is ready
  useEffect(() => {
    if (recorder) {
      setMuted(false);
      recorder.setRecordingGain(1);
    }
  },
  [recorder]);

  const amplitudePercent = amplitude / 255;
  const maxAmplitude = 0.3; // for scaling
  const minDiameter = 20; // minimum diameter of the circle in pixels
  const maxDiameter = 200; // increased maximum diameter to ensure overflow
  
  var diameter = minDiameter + (maxDiameter - minDiameter) * (amplitudePercent / maxAmplitude);
  if (muted) {
    diameter = 20;
  }

  return (
    <div className="w-full h-full flex items-center">
      <div className="w-full h-6 rounded-md relative overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center">
          <div
            className={`rounded-full transition-all duration-100 ease-out hover:cursor-pointer ${muted ? 'bg-gray-200' : 'bg-red-400'}`}
            onClick={toggleMute}
            style={{
              width: `${diameter}px`,
              height: `${diameter}px`,
            }}
          ></div>
        </div>
      </div>
    </div>
  );
};

const TextOutput = ({ warmupComplete, completedSentences, pendingSentence }) => {
  const containerRef = useRef(null);
  const allSentences = [...completedSentences, pendingSentence];
  if (pendingSentence.length === 0 && allSentences.length > 1) {
    allSentences.pop();
  }

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [completedSentences, pendingSentence]);

  return (
    <div ref={containerRef} className="flex flex-col-reverse overflow-y-auto max-h-64 pr-2">
      {warmupComplete ? (
        allSentences.map((sentence, index) => (
          <p key={index} className="text-gray-300 my-2">{sentence}</p>
        )).reverse()
      ) : (
        <p className="text-gray-400 animate-pulse">Warming up model...</p>
      )}
    </div>
  );
};



const container = document.getElementById("react");
ReactDOM.createRoot(container).render(<App />);