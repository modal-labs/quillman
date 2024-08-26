import RecorderNode from "./recorder-node.js";
import { float32ArrayToWav } from "./converter.js";
const { useState, useEffect, useRef } = React;

function App() {
  const [session, setSession] = useState(false);
  const [isUserTalking, setIsUserTalking] = useState(false);

  const socketRef = useRef(null);
  const recorderNodeRef = useRef(null);
  const audioContextRef = useRef(null);
  const onMicBufferReceiveRef = useRef(null);
  const audioOutQueue = useRef([]);
  const isPlaying = useRef(false);

  // create a websocket connection
  function openWebsocket(onMessageCallback) {
    const socket = new WebSocket('wss://erik-dunteman--quillman-proto-web-dev.modal.run/pipeline');
    socket.onopen = () => {
      console.log('WebSocket connection established');
    };
    socket.onclose = () => {
      console.log('WebSocket connection closed');
    };
    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    socket.onmessage = onMessageCallback;
    return socket;
  }
  
  // audio player
  const playNextInQueue = async () => {
    if (audioOutQueue.current.length === 0 || isPlaying.current) {
      // prevent playing if we're already playing or there's nothing in the queue
      return;
    }
    isPlaying.current = true;
    const arrayBuffer = audioOutQueue.current.shift();
    try {
      const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer);
      console.log("Playing audio");
      const source = audioContextRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContextRef.current.destination);
      source.onended = () => {
        console.log('Audio playback ended');
        isPlaying.current = false;
        playNextInQueue();
      };
      source.start();
    } catch (error) {
      console.error("Error decoding audio data:", error);
      isPlaying.current = false;
      playNextInQueue();
    }
  };

  const onWebsocketMessage = async (event) => {
    console.log("Received response from server");
    if (event.data instanceof Blob) {
      const arrayBuffer = await event.data.arrayBuffer();
      audioOutQueue.current.push(arrayBuffer);
      playNextInQueue();
    }
  };

  function onSilence() {
    setIsUserTalking(false);
  }

  function onTalking() {
    setIsUserTalking(true);
  }

  // Update onMicBufferReceiveRef whenever session changes
  useEffect(() => {
    onMicBufferReceiveRef.current = async (buffer) => {
      // ignore if not in a session
      if (session === false) {
        return;
      }

      if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
        console.log("Websocket not open, this is bad");
        return; 
      }

      // we want to to run the pipeline.
      const wav_buffer = float32ArrayToWav(buffer, 48000);

      // open socket for this pipeline
      socketRef.current.send(wav_buffer);
      console.log("Sent wav segment to server");
    };
  }, [session]);

  async function startSession() {
    socketRef.current = openWebsocket(onWebsocketMessage);
    await new Promise((resolve, reject) => {
      socketRef.current.onopen = resolve;
      socketRef.current.onerror = reject;
    });
    setSession(true);
  }

  function endSession() {
    socketRef.current.send(new TextEncoder().encode('<END>'));
    setSession(false);
  }
  
  // set up local audio recording process
  useEffect(() => {
    async function onMount() {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const context = new AudioContext();
      audioContextRef.current = context;
      const source = context.createMediaStreamSource(stream);
  
      await context.audioWorklet.addModule("processor.js");
      const recorderNode = new RecorderNode(
        context,
        (...args) => onMicBufferReceiveRef.current(...args),
        onSilence,
        onTalking,
      );
      recorderNodeRef.current = recorderNode;
  
      source.connect(recorderNode);
      recorderNode.connect(context.destination);
    }
    onMount();
  }, []);

  return (
    <div className="app">
      <h1>QuiLLMan</h1>
      {isUserTalking ? <h1>User Talking</h1> : <h1>User Silent</h1>}
      {session ? <h1>Session Active</h1> : <h1>Session Inactive</h1>}
      {session ? <button onClick={endSession}>End Session</button> : <button onClick={startSession}>Start Session</button>}
    </div>
  );
}

const container = document.getElementById("react");
ReactDOM.createRoot(container).render(<App />);