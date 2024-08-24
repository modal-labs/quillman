import RecorderNode from "./recorder-node.js";
const { useState, useEffect, useRef } = React;

function App() {
  const [message, setMessage] = useState('');
  const recorderNodeRef = useRef(null);
  const [isMicOn, setIsMicOn] = useState(true);
  const [isUserTalking, setIsUserTalking] = useState(false);
  const socketRef = useRef(null);
  const audioContextRef = useRef(null);

  function setupWebSocket() {
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

    socket.onmessage = async (event) => {
      if (event.data instanceof Blob) {
        console.log('Received audio data from server');
        const arrayBuffer = await event.data.arrayBuffer();
        const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer);
        playAudio(audioBuffer);
      } else {
        console.log('Received message from server:', event.data);
      }
    };

    return socket;
  }

  function playAudio(audioBuffer) {
    const source = audioContextRef.current.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContextRef.current.destination);
    source.onended = () => {
      console.log('Audio playback ended');
    };
    source.start();
  }

  async function onSegmentRecv(buffer) {
    console.log("Segment received", buffer);

    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      console.log('WebSocket is not open. Attempting to connect...');
      socketRef.current = setupWebSocket();
      
      await new Promise((resolve, reject) => {
        socketRef.current.onopen = resolve;
        socketRef.current.onerror = reject;
      });
    }

    // Send the buffer over WebSocket
    socketRef.current.send(buffer);
  }

  function onSilence() {
    console.log("Silence detected");
    setIsUserTalking(false);
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(new TextEncoder().encode('<END>'));
    }
  }

  function onTalking() {
    if (!isMicOn) {
      return;
    }
    console.log("Talking detected");
    setIsUserTalking(true);
  }

  async function onMount() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const context = new AudioContext();
    audioContextRef.current = context;
    const source = context.createMediaStreamSource(stream);

    await context.audioWorklet.addModule("processor.js");
    const recorderNode = new RecorderNode(
      context,
      onSegmentRecv,
      onSilence,
      onTalking,
    );
    recorderNodeRef.current = recorderNode;

    source.connect(recorderNode);
    recorderNode.connect(context.destination);

    // Set up WebSocket connection
    socketRef.current = setupWebSocket();
  }
  
  useEffect(() => {
    onMount();
    return () => {
      // Close WebSocket connection when component unmounts
      if (socketRef.current) {
        socketRef.current.close();
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    if (recorderNodeRef.current) {
      if (isMicOn) {
        recorderNodeRef.current.start();
      } else {
        recorderNodeRef.current.stop();
      }
    }
  }, [isMicOn]);

  const toggleMic = () => setIsMicOn(!isMicOn);

  return (
    <div className="app">
      <h1>QuiLLMan</h1>
      {isUserTalking ? <h1>User Talking</h1> : <h1>User Silent</h1>}
      {isMicOn ? <h1>Mic ON</h1> : <h1>Mic OFF</h1>}
      <button onClick={toggleMic}>{isMicOn ? 'Turn Mic Off' : 'Turn Mic On'}</button>
    </div>
  );
}

const container = document.getElementById("react");
ReactDOM.createRoot(container).render(<App />);