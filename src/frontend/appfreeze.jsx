import RecorderNode from "./recorder-node.js";
import { float32ArrayToWav } from "./converter.js";
const { useState, useEffect, useRef } = React;

// const backendUrl = "https://erik-dunteman--quillman-proto-web-dev.modal.run";
const backendUrl = "erik-dunteman--quillman-proto-web.modal.run";

function App() {
  // APP STATES = ["SETUP", "WAITING_FOR_USER", "RECORDING", "GENERATING"]
  // SETUP => WAITING_FOR_USER => RECORDING => GENERATING => SETUP
  // SETUP: ensure recorder node, websocket connection, and /prewarm endpoint are all ready
  // -> if setup all good, proceed to WAITING_FOR_USER
  // WAITING_FOR_USER: mic is unmuted, but user has not yet started speaking
  // -> if we get the first onTalking signal, proceed to RECORDING
  // RECORDING: user has started speaking, but we haven't received the silance signal yet. mic remains unmuted.
  // -> once we get the onSilence signal, proceed to GENERATING
  // GENERATING: we have received the silence signal, and are generating the response.



  const [awaitingResponse, setAwaitingResponse] = useState(false);
  const isRecordingSessionRef = useRef(false);

  const [micAmplitude, setMicAmplitude] = useState(0);
  const [micThreshold, setMicThreshold] = useState(0.1);
  const [whisperStatus, setWhisperStatus] = useState(false);
  const [zephyrStatus, setZephyrStatus] = useState(false);
  const [xttsStatus, setXttsStatus] = useState(false);

  const [history, setHistory] = useState([
    { isUser: false, text: "Speak into your microphone to talk to me..." },
  ]);
  const [botAwake, setBotAwake] = useState(false);

  useEffect(() => {
    // call https://erik-dunteman--quillman-proto-web-dev.modal.run/prewarm
    // to prewarm the LLM and TTS models
    async function prewarm() {
      await fetch(`https://${backendUrl}/prewarm`);
      setBotAwake(true);
    }
    prewarm();
  }, []);

  // poll https://erik-dunteman--quillman-proto-web-dev.modal.run/status
  // to check if models are warm
  // useEffect(() => {
  //   const intervalId = setInterval(async () => {
  //     try {
  //       const response = await fetch(`https://${backendUrl}/status`);
  //       if (!response.ok) {
  //         throw new Error("Error occurred during status check: " + response.status);
  //       }
  //       const data = await response.json();
  //       setWhisperStatus(data.whisper);
  //       setZephyrStatus(data.zephyr);
  //       setXttsStatus(data.xtts);
  //     } catch (error) {
  //       console.error(error);
  //     }
  //   }, 1000);
  //   return () => clearInterval(intervalId);
  // }, []);

  const socketRef = useRef(null);
  const recorderNodeRef = useRef(null);
  const audioContextRef = useRef(null);
  const onMicBufferReceiveRef = useRef(null);
  const audioOutQueue = useRef([]);
  const isPlaying = useRef(false);

  // create a websocket connection
  function openWebsocket(onMessageCallback) {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(`wss://${backendUrl}/pipeline`);
      socket.onopen = () => {
        console.log('WebSocket connection established');
        resolve(socket);
      };
      socket.onclose = () => {
        console.log('WebSocket connection closed');
      };
      socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(error);
      };
      socket.onmessage = onMessageCallback;
      return socket;
    }
  )};

  // audio player
  const playNextInQueue = async () => {
    if (isPlaying.current ) {
      // there's already an audio player working on the queue
      return;
    }
    if (audioOutQueue.current.length === 0) {
      // this player has reached the end of the queue

      // prepare for next round of audio
      socketRef.current = await openWebsocket(onWebsocketMessage);

      setAwaitingResponse(false);
      return;
    }
    isPlaying.current = true;
    const arrayBuffer = audioOutQueue.current.shift();
    try {
      const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer);
      const source = audioContextRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContextRef.current.destination);
      source.onended = () => {
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
    if (event.data instanceof Blob){
      const arrayBuffer = await event.data.arrayBuffer();
      
      // try to parse out json, else if it fails, it's a wav
      try {
        const data = JSON.parse(new TextDecoder().decode(arrayBuffer));
        if (data.type === "text") {        
          setHistory((prevHistory) => {
            const lastMessage = prevHistory[prevHistory.length - 1];
        
            if (lastMessage && lastMessage.isUser) {
              // If the last message is from the user, add a new bot message
              return [...prevHistory, { isUser: false, text: data.value }];
            } else if (lastMessage && !lastMessage.isUser) {
              // If the last message is from the bot, append to it
              const updatedHistory = [...prevHistory];
              updatedHistory[updatedHistory.length - 1] = {
                ...lastMessage,
                text: lastMessage.text + data.value
              };
              return updatedHistory;
            } else {
              // If there's no history or in any other case, add a new bot message
              return [...prevHistory, { isUser: false, text: data.value }];
            }
          });
        } else if (data.type === "transcript") {
          const transcript = data.value;
          setHistory((history) => [...history, { isUser: true, text: transcript }]);
        }
      } catch {
        audioOutQueue.current.push(arrayBuffer);
        playNextInQueue();
      }
    }
  };

  function onTalking() {
    maybeStartRecordingSession();
  }

  function onSilence() {
    endRecordingSession();
  }

  function onAmplitude(amplitude) {
    setMicAmplitude(amplitude);
  }

  async function onBufferRecived(buffer) {
    // ignore if not in a recordingSession
    if (isRecordingSessionRef.current === false) {
      console.log("Buffer received but not recording, ignoring");
      return;
    }

    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      console.log("Websocket not open yet, this is unexpected");
      return;
    }

    const wav_buffer = float32ArrayToWav(buffer, 48000);

    // first send wav signal, then wav data
    socketRef.current.send(new TextEncoder().encode(`{"type": "wav"}`));
    socketRef.current.send(wav_buffer);
    console.log("Sent wav segment to server");
  };

  async function maybeStartRecordingSession() {
    if (awaitingResponse || isRecordingSessionRef.current) {
      return;
    }

    isRecordingSessionRef.current = true;
  }

  function endRecordingSession() {
    if (isRecordingSessionRef.current === false) {
      return;
    }
    socketRef.current.send(new TextEncoder().encode(`{"type": "end"}`));
    console.log("Sent end signal to server");
    setAwaitingResponse(true);
    isRecordingSessionRef.current = false;
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
        onBufferRecived,
        onTalking,
        onSilence,
        onAmplitude,
      );
      recorderNodeRef.current = recorderNode;
  
      source.connect(recorderNode);
      recorderNode.connect(context.destination);

      // set up first websocket connection
      socketRef.current = await openWebsocket(onWebsocketMessage);
    }
    onMount();
  }, []);

  const updateMicThreshold = (value) => {
    // update both in the recorder node and UI state
    recorderNodeRef.current.updateThreshold(value);
    setMicThreshold(value);
  };

  return (
    <div className="app absolute h-screen w-screen flex text-white">
      <div className="bg-gray-900 w-1/6 flex flex-col items-center p-3">
        {/* sidebar */}
        <h1>Quillman</h1>
        <div className="flex flex-col gap-2 w-full">
          <div className="flex justify-between items-center">
            <h1>Whisper</h1>
            <div className={`${whisperStatus ? 'text-green-500' : 'text-red-500'} text-2xl`}>
              ●
            </div>
          </div>
          <div className="flex justify-between items-center">
            <h1>Zephyr LLM</h1>
            <div className={`${zephyrStatus ? 'text-green-500' : 'text-red-500'} text-2xl`}>
              ●
            </div>
          </div>
          <div className="flex justify-between items-center">
            <h1>XTTS</h1>
            <div className={`${xttsStatus ? 'text-green-500' : 'text-red-500'} text-2xl`}>
              ●
            </div>
          </div>
          <button onClick={() => recorderNodeRef.current.mute()}>Mute</button>
          <button onClick={() => recorderNodeRef.current.unmute()}>Unmute</button>
          <div>
            <MicLevels micAmplitude={micAmplitude} micThreshold={micThreshold} isRecordingSession={isRecordingSessionRef.current} updateMicThreshold={updateMicThreshold} />
          </div>
        </div>
      </div>
      <div className="bg-gray-700 w-5/6 flex flex-col items-center p-3 px-6">
        <h1>Chat</h1>
        {isRecordingSessionRef.current ? <h1>Recording</h1> : <h1>Not Recording</h1>}
        {botAwake ? <>
          {history.map(({ isUser, text }) => (
            <ChatMessage text={text} isUser={isUser} key={text} />
          ))}
        </> : 
          <WakeupMessage />
        }
      </div>
    </div>
  );
}

function MicLevels({ micAmplitude, micThreshold, updateMicThreshold, isRecordingSession }) {
  const maxAmplitude = 0.2; // for scaling

  return (
    <div className="w-full max-w-md mx-auto py-4 space-y-4">
      <div className={`relative h-4 rounded-full overflow-hidden` + (isRecordingSession ? ' bg-green-500' : ' bg-gray-400')}>
        
        <div 
          className={`absolute top-0 left-0 h-full transition-all duration-100 ease-out bg-blue-500`}
          style={{ width: `${(micAmplitude / maxAmplitude) * 100}%` }}
        ></div>
        <div 
          className="absolute top-0 h-full w-0.5 bg-white"
          style={{ left: `${(micThreshold / maxAmplitude) * 100}%` }}
        ></div>
      </div>
      
      <div className="space-y-2">
        <label htmlFor="threshold-slider" className="block text-sm font-medium text-gray-300">
          Adjust Mic Sensitivity:
        </label>
        <input
          type="range"
          id="threshold-slider"
          min={0}
          max={maxAmplitude}
          step={0.001}
          value={micThreshold}
          onChange={(e) => updateMicThreshold(Number(e.target.value))}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
        />
      </div>
    </div>
  );
}


function WakeupMessage() {
  const wakeupMessages = ["One second while I wake up...", "I'm coming online soon, I promise!", "I'm still not ready yet, but should be good to talk soon." , "Ooof this is awkward, give me a tiny bit more..."];
  const [wakeupMessageIndex, setWakeupMessageIndex] = useState(0);
  
  useEffect(() => {
    const intervalId = setInterval(() => {
      let next = wakeupMessageIndex + 1;
      if (next >= wakeupMessages.length) {
        next = 0;
      }
      setWakeupMessageIndex(next);
    }, 20_000);
    return () => clearInterval(intervalId);
  }, [wakeupMessageIndex]);

  return (
    <div className="w-full">
      <div className="text-base gap-4 p-4 flex justify-start">
        <div className="flex items-center gap-2 max-w-[600px] flex-row">
          <div
            className="flex items-center justify-center w-8 h-8 min-w-8 min-h-8 fill-primary"
          >
            <BotIcon />
          </div>
          <div className="whitespace-pre-wrap rounded-[16px] px-3 py-1.5 bg-zinc-800 border text-left pulse">
            {wakeupMessages[wakeupMessageIndex]}
          </div>
        </div>
      </div>
    </div>
  );
}

function ChatMessage({ text, isUser }) {
  return (
    <div className="w-full">
      <div className={`text-base gap-4 p-4 flex ${isUser ? 'justify-end' : 'justify-start'}`}>
        <div className={`flex items-center gap-2 max-w-[600px] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
          <div
            className={`flex items-center justify-center w-8 h-8 min-w-8 min-h-8 ${
              isUser ? "fill-yellow-500" : "fill-primary"
            }`}
          >
            {isUser ? <UserIcon /> : <BotIcon />}
          </div>
          <div className={`whitespace-pre-wrap rounded-[16px] px-3 py-1.5 bg-zinc-800 border ${isUser ? 'text-right' : 'text-left'}`}>
            {text}
          </div>
        </div>
      </div>
    </div>
  );
}


function BotIcon() {
  return (
    <svg
      className="w-full h-full"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 640 512"
    >
      {/*! Font Awesome Pro 6.4.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license (Commercial License) Copyright 2023 Fonticons, Inc.*/}
      <path d="M320 0c17.7 0 32 14.3 32 32V96H472c39.8 0 72 32.2 72 72V440c0 39.8-32.2 72-72 72H168c-39.8 0-72-32.2-72-72V168c0-39.8 32.2-72 72-72H288V32c0-17.7 14.3-32 32-32zM208 384c-8.8 0-16 7.2-16 16s7.2 16 16 16h32c8.8 0 16-7.2 16-16s-7.2-16-16-16H208zm96 0c-8.8 0-16 7.2-16 16s7.2 16 16 16h32c8.8 0 16-7.2 16-16s-7.2-16-16-16H304zm96 0c-8.8 0-16 7.2-16 16s7.2 16 16 16h32c8.8 0 16-7.2 16-16s-7.2-16-16-16H400zM264 256a40 40 0 1 0 -80 0 40 40 0 1 0 80 0zm152 40a40 40 0 1 0 0-80 40 40 0 1 0 0 80zM48 224H64V416H48c-26.5 0-48-21.5-48-48V272c0-26.5 21.5-48 48-48zm544 0c26.5 0 48 21.5 48 48v96c0 26.5-21.5 48-48 48H576V224h16z" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg
      className="w-full h-full"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 448 512"
    >
      {/*! Font Awesome Pro 6.4.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license (Commercial License) Copyright 2023 Fonticons, Inc.*/}
      <path d="M224 256A128 128 0 1 0 224 0a128 128 0 1 0 0 256zm-45.7 48C79.8 304 0 383.8 0 482.3C0 498.7 13.3 512 29.7 512H418.3c16.4 0 29.7-13.3 29.7-29.7C448 383.8 368.2 304 269.7 304H178.3z" />
    </svg>
  );
}


const container = document.getElementById("react");
ReactDOM.createRoot(container).render(<App />);