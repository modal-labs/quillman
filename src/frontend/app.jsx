const { useRef, useEffect, useState } = React;

const baseURL = "" // points to whatever is serving this app (eg your -dev.modal.run for modal serve, or .modal.run for modal deploy)

const getBaseURL = () => {
  // return "wss://erik-dunteman--quillman-moshi-web-dev.modal.run/ws"; // temporary erik!

  // use current web app server domain to construct the url for the moshi app
  const currentURL = new URL(window.location.href);
  let hostname = currentURL.hostname;
  hostname = hostname.replace('-web', '-moshi-web');
  const wsProtocol = currentURL.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${hostname}/ws`; 
}

const CenteredSquareUI = ({ warmupComplete, completedSentences, pendingSentence }) => {
  const [contentHeight, setContentHeight] = useState('auto');
  const allSentences = [...completedSentences, pendingSentence];
  if (pendingSentence.length === 0 && allSentences.length > 1) {
    allSentences.pop();
  }
  const displaySentences = allSentences;
  return (
    <div className="bg-gray-900 text-white min-h-screen flex items-center justify-center p-4">
      <div className="bg-gray-800 rounded-lg shadow-lg w-full max-w-xl p-6">
        <div 
          className="overflow-y-auto transition-height duration-300 ease-in-out flex flex-col-reverse max-h-64"
        >
          <div className="flex flex-col-reverse ">
            {warmupComplete ? (
              displaySentences.map((sentence, index) => (
                <p key={index} className="text-gray-300 my-2">{sentence}</p>
              )).reverse()
            ) : (
              <p className="text-gray-400 animate-pulse">Warming up model...</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};


const App = () => {
  const socketRef = useRef(null);
  const [completedSentences, setCompletedSentences] = useState([]);
  const [pendingSentence, setPendingSentence] = useState('');
  const [warmupComplete, setWarmupComplete] = useState(false);

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

    recorder.start().then(() => console.log("Recording started"));
  };

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
        // console.log("Received audio data", payload.byteLength, "bytes");
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

  const allSentences = [...completedSentences, pendingSentence];
  const displaySentences = allSentences.slice(-10);

  return CenteredSquareUI({ warmupComplete, completedSentences, pendingSentence });
}




const container = document.getElementById("react");
ReactDOM.createRoot(container).render(<App />);