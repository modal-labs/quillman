const { createMachine} = XState;
const { useMachine } = XStateReact;
const { useRef, useEffect, useState } = React;
import RecorderNode from "./recorder-node.js";
import {float32ArrayToWav} from "./converter.js";

const baseURL = "" // points to whatever is serving this app (eg your -dev.modal.run for modal serve, or .modal.run for modal deploy)

// We use XState to manage the state of the app, transitioning between states:
// - SETUP: warming up models, setting up audio context, etc.
// - IDLE: waiting for user to speak loud enough to trigger the recording
// - RECORDING: recording audio until user has been silent for a certain amount of time. Audio begins streaming to the server.
// - GENERATING: /pipeline GENERATEs a response and streams it back to the client. Ends once final audio is played.
const voiceChatMachine = createMachine({
  id: 'voiceChat',
  initial: 'SETUP',
  context: {
    websocket: null,
    recorderNode: null,
    audioContext: null,
  },
  states: {
    SETUP: {
      on: {
        SETUP_COMPLETE: 'IDLE'
      },
      invoke: {
        src: 'doSetup',
        onDone: {
          actions: ['unmuteMic'],
          target: 'IDLE',
        },
      }
    },
    IDLE: {
      on: {
        START_RECORDING: 'RECORDING'
      }
    },
    RECORDING: {
      on: {
        STOP_RECORDING: {
          target: 'GENERATING',
          actions: ['muteMic']
        }
      }
    },
    GENERATING: {
      on: {
        GENERATION_COMPLETE: 'SETUP',
      }
    }
  }
});

const App = () => {
  const [chatHistory, setChatHistory] = useState([{
    role: "assistant",
    content: "Hi! I'm a language model running on Modal. Talk to me using your microphone, and remember to turn your speaker volume up!"
  }]);
  const [micAmplitude, setMicAmplitude] = useState(0);
  const [micThreshold, setMicThreshold] = useState(0.05);

  // Due to how the recorder node callback closures work, we need to use Refs to ensure the callbacks use the latest values
  const sendRef = useRef();
  const stateRef = useRef();
  const chatHistoryRef = useRef(chatHistory);
  const playQueueRef = useRef([]);
  const isPlayingRef = useRef(false);

  const updateMicThreshold = (value) => {
    // update both in the recorder node and UI state
    stateRef.current.context.recorderNode.updateThreshold(value);
    setMicThreshold(value);
  };

  // Called in SETUP state
  const setupAudio = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);

    const onBufferReceived = async (buffer) => {
      if (!stateRef.current.matches('RECORDING')) {
        return;
      }

      const wav_blob = float32ArrayToWav(buffer, 48000);
      const array_buffer = await wav_blob.arrayBuffer();
      const wav_base64 = btoa(
        new Uint8Array(array_buffer)
          .reduce((data, byte) => data + String.fromCharCode(byte), '')
      );
      stateRef.current.context.websocket.send(new TextEncoder().encode(`{"type": "wav", "value": "${wav_base64}"}`));
      console.log("Sent wav segment to server");
    }

    // Callback for when the user mic exceeds the threshold
    const onTalking = () => {
      // state transition only valid in IDLE state, so only relevant in first onTalking
      sendRef.current("START_RECORDING");
    }

    // Callback for when the user has been below threshold for the silence period
    const onSilence = () => {
      if (!stateRef.current.matches('RECORDING')) {
        return;
      }

      // Prepare to transition to the GENERATING state

      // Send the chat history to the server and end signal to the server. Truncate the history to the last 10 messages.
      const historyMessage = `{"type": "history", "value": ${JSON.stringify(chatHistoryRef.current.slice(-10))}}`;
      stateRef.current.context.websocket.send(new TextEncoder().encode(historyMessage));        
      stateRef.current.context.websocket.send(new TextEncoder().encode(`{"type": "end"}`));

      // Transition to the GENERATING state
      sendRef.current("STOP_RECORDING");
    }

    // Callback for sending amplitude from recorder node to the UI
    const onAmplitude = (amplitude) => {
      setMicAmplitude(amplitude);
    }

    // Recorder node expects the callbacks: onBufferReceived, onTalking, onSilence, onAmplitude
    await audioContext.audioWorklet.addModule("processor.js");
    const recorderNode = new RecorderNode(
      audioContext,
      onBufferReceived,
      onTalking,
      onSilence,
      onAmplitude,
    );

    source.connect(recorderNode);
    recorderNode.connect(audioContext.destination);
    console.log("Audio setup complete");
    return { recorderNode, audioContext };
  }

  // Called in SETUP state
  const openWebsocket = async (onWebsocketMessage) => {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(`${baseURL}/pipeline`);
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
      socket.onmessage = onWebsocketMessage;
      return socket;
    });
  }

  // Called in GENERATING state, when we're waiting for the server to send us a response
  const onWebsocketMessage = async (event) => {
    if (!stateRef.current.matches('GENERATING')) {
      return;
    }

    if (event.data instanceof Blob){
      const arrayBuffer = await event.data.arrayBuffer();

      // else parse json
      const data = JSON.parse(new TextDecoder().decode(arrayBuffer));
      if (data.type === "wav") {
        const wavBase64 = data.value;
        const wavBinary = atob(wavBase64);
        const wavBytes = new Uint8Array(wavBinary.length);
        for (let i = 0; i < wavBinary.length; i++) {
          wavBytes[i] = wavBinary.charCodeAt(i);
        }
        playQueueRef.current.push(wavBytes.buffer);

        // // // Create a Blob from the Uint8Array
        // const wavBlob = new Blob([wavBytes], { type: 'audio/wav' });
        // playQueueRef.current.push(wavBlob);
        return;
      } else if (data.type === "text") {
        console.log("Received bot reply:", data.value);
        // Append bot reply to chat history
        setChatHistory(prevHistory => {
          let lastMessage = prevHistory[prevHistory.length - 1];
          if (lastMessage.role === "user") {
            return [...prevHistory, { role: "assistant", content: data.value }];
          } else {
            const updatedHistory = [...prevHistory];
            updatedHistory[updatedHistory.length - 1] = {
              ...lastMessage,
              content: lastMessage.content + "\n" + data.value
            };
            return updatedHistory;
          }
        });
      } else if (data.type === "transcript") {
        // Append user transcript to chat history
        console.log("Received user transcript:", data.value);
        setChatHistory(prevHistory => [...prevHistory, {role: "user", content: data.value}]);
      }
    };
  }

  // Audio player always runs in the background during GENERATING state
  // It plays the wavs sent by the server.
  useEffect(() => {
    const intervalId = setInterval(async () => {
      if (stateRef.current.matches('GENERATING') && !isPlayingRef.current && playQueueRef.current.length > 0) {
        isPlayingRef.current = true;
        const arrayBuffer = playQueueRef.current.shift();
        if (arrayBuffer) {
          try {
            const audioBuffer = await stateRef.current.context.audioContext.decodeAudioData(arrayBuffer);
            const source = stateRef.current.context.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(stateRef.current.context.audioContext.destination);
            source.onended = () => {
              isPlayingRef.current = false;
              if (playQueueRef.current.length === 0 && stateRef.current.context.websocket.readyState === WebSocket.CLOSED) {
                // on empty queue and websocket closed, transition to the SETUP state to start a new websocket connection
                sendRef.current("GENERATION_COMPLETE");
                return;
              }
            };
            source.start();
          } catch (error) {
            console.error("Error decoding audio data:", error);
          }
        }
      }
    }, 200);
    return () => clearInterval(intervalId);
  }, []);

  const [state, send] = useMachine(voiceChatMachine, {
    actions: {
      unmuteMic: (context, event) => {
        console.log("Unmuting mic");
        context.recorderNode.unmute();
      },
      muteMic: (context, event) => {
        console.log("Muting mic");
        context.recorderNode.mute();
      },
    },
    services: {
      doSetup: async (context) => {
        console.log('Setting up services');

        // Setup audio if not already setup
        if (!context.recorderNode) {
          const { recorderNode, audioContext } = await setupAudio();
          context.audioContext = audioContext;
          context.recorderNode = recorderNode;
        }

        // Ensure warmup
        await fetch(`${baseURL}/prewarm`);

        // Each new bot response is a new websocket session, so prep the connection for the upcoming session.
        const socket = await openWebsocket(onWebsocketMessage);
        context.websocket = socket;

        return Promise.resolve(context);
      },
    }
  });

  sendRef.current = send;
  stateRef.current = state;
  chatHistoryRef.current = chatHistory;

  return (
    <div className="app absolute h-screen w-screen flex text-white">
      <div className="flex w-full">
        <div className="w-1/6">
          <Sidebar stateRef={stateRef} micAmplitude={micAmplitude} micThreshold={micThreshold} updateMicThreshold={updateMicThreshold} />
        </div>
        <div className="w-5/6 flex-grow overflow-auto flex-col items-center p-3 px-6">
          <h1 className="text-2xl">Chat</h1>
            {chatHistory.map(({ role, content }) => (
              <ChatMessage content={content} role={role} key={content} />
            ))}
            <UserHint state={stateRef.current} />
            <div className="h-5/6 flex-shrink-0"></div>
        </div>
      </div>
    </div>
  );
}

const ChatMessage = ({ content, role }) => {
  return (
    <div className="w-full">
      <div className={`text-base p-4 flex ${role == "user" ? 'justify-end' : 'justify-start'}`}>
        <div className="flex items-start gap-2 max-w-[600px] w-fit">
          <div
            className={`flex-shrink-0 flex items-center justify-center w-8 h-8 mt-1 ${
              role == "user" ? "fill-yellow-500 order-last" : "fill-primary"
            }`}
          >
            {role == "user" ? <UserIcon /> : <BotIcon />}
          </div>
          <div className="flex-grow whitespace-pre-wrap rounded-[16px] p-3 bg-zinc-800 border text-left">
            {content}
          </div>
        </div>
      </div>
    </div>
  );
}

const UserHint = ({ state }) => {
  const [firstSetup, setFirstSetup] = useState(true);

  useEffect(() => {
    if (state.matches('IDLE') && firstSetup) {
      setFirstSetup(false);
    }
  }, [state, firstSetup]);

  if (state.matches('SETUP') && !firstSetup) {
    return null;
  }

  if (state.matches("GENERATING")) {
    return null;
  }

  let hintText = "";
  if (state.matches('SETUP') && firstSetup) {
    hintText = "Waking up models...";
  } else if (state.matches('IDLE')) {
    hintText = "Ready to talk!";
  } else if (state.matches('RECORDING')) {
    hintText = "Listening";
  }

  if (!hintText) {
    return null;
  }

  return (
    <div className="w-full">
      <div className="text-md p-4 flex justify-center">
        <div className="flex items-start gap-2 max-w-[600px] w-fit">
          <div className="flex-grow whitespace-pre-wrap rounded-[16px] p-3 bg-zinc-800/50 pulse">
            {hintText}
          </div>
        </div>
      </div>
    </div>
  );
}

const Sidebar = ({ stateRef, micAmplitude, micThreshold, updateMicThreshold }) => {
  const [whisperStatus, setWhisperStatus] = useState(false);
  const [llamaStatus, setLlamaStatus] = useState(false);
  const [xttsStatus, setXttsStatus] = useState(false);
  
  // Backend status monitor that always runs in the background
  useEffect(() => {
    const intervalId = setInterval(async () => {
      try {
        const response = await fetch(`${baseURL}/status`);
        if (!response.ok) {
          throw new Error("Error occurred during status check: " + response.status);
        }
        const data = await response.json();
        setWhisperStatus(data.whisper);
        setLlamaStatus(data.llama);
        setXttsStatus(data.xtts);

        // stop once all services are up
        if (data.whisper && data.llama && data.xtts) {
          clearInterval(intervalId);
        }
      } catch (error) {
        console.error(error);
      }
    }, 1000);
    return () => clearInterval(intervalId);
  }, []);
  
  return (
    <div className="bg-zinc-800 fixed w-1/6 top-0 bottom-0 flex flex-col items-center p-4">
      <h1 className="text-3xl">QuiLLMan</h1>
      <div className="flex flex-col gap-2 w-full mt-8 text-md">
        <h2 className="text-xl">Service Status</h2>
        <div className="flex justify-between items-center">
          <p>Whisper</p>
          {whisperStatus ? (
            <div className="text-white text-xl">👂</div>
          ) : (
            <div className="text-red-500 text-xl">●</div>
          )}
        </div>
        <div className="flex justify-between items-center">
          <p>Llama</p>
          {llamaStatus ? (
            <div className="text-white text-xl">🧠</div>
          ) : (
            <div className="text-red-500 text-xl">●</div>
          )}
        </div>
        <div className="flex justify-between items-center">
          <p>XTTS</p>
          {xttsStatus ? (
            <div className="text-white text-xl">👄</div>
            ) : (
            <div className="text-red-500 text-xl">●</div>
          )}
        </div>
      </div>
      <div className="mt-8 w-full">
        <MicLevels micAmplitude={micAmplitude} micThreshold={micThreshold} isRecordingState={stateRef.current.matches('RECORDING')} updateMicThreshold={updateMicThreshold} />
      </div>
      <a
        className="items-center flex justify-center mt-auto"
        href="https://modal.com"
        target="_blank"
        rel="noopener noreferrer"
      >
        <footer className="flex items-center w-42 p-1 mb-6 rounded border">
          <span className="p-1 text-md">
            <strong>built with</strong>
          </span>
          <img className="h-12 w-24" src="./modal-logo.svg" alt="Modal logo" />
        </footer>
      </a>
    </div>
  );
}

const MicLevels = ({ micAmplitude, micThreshold, isRecordingState, updateMicThreshold }) => {
  const maxAmplitude = 0.2; // for scaling

  return (
    <div className="w-full max-w-md mx-auto space-y-2">
      <h1  className="text-xl">Mic Settings</h1>
      <label className="block text-sm font-medium text-gray-300">Mic Level</label>
      <div className={`relative h-4 rounded-full overflow-hidden` + (isRecordingState ? ' bg-primary' : ' bg-zinc-600')}>
        <div 
          className={`absolute top-0 left-0 h-full transition-all duration-100 ease-out bg-zinc-200`}
          style={{ width: `${(micAmplitude / maxAmplitude) * 100}%` }}
        ></div>
        <div 
          className="absolute top-0 h-full w-0.5 bg-white"
          style={{ left: `${(micThreshold / maxAmplitude) * 100}%` }}
        ></div>
      </div>
      
      <div className="space-y-2">
        <label htmlFor="threshold-slider" className="block text-sm font-medium text-gray-300">
          Threshold:
        </label>
        <input
          type="range"
          id="threshold-slider"
          min={0}
          max={maxAmplitude}
          step={0.001}
          value={micThreshold}
          onChange={(e) => updateMicThreshold(Number(e.target.value))}
          className="w-full h-2 bg-zinc-600 rounded-lg appearance-none cursor-pointer"
        />
      </div>
    </div>
  );
}

const BotIcon = () => {
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

const UserIcon = () => {
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