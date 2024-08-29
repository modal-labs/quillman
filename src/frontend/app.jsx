const { createMachine, assign, spawn} = XState;
const { useMachine } = XStateReact;
const { useRef, useEffect, useState } = React;
import RecorderNode from "./recorder-node.js";
import {float32ArrayToWav} from "./converter.js";

// const backendUrl = "https://erik-dunteman--quillman-proto-web-dev.modal.run";
const backendUrl = "erik-dunteman--quillman-proto-web.modal.run";


const voiceChatMachine = createMachine({
  id: 'voiceChat',
  initial: 'SETUP',
  context: {
    websocket: null,
    recorderNode: null,
    audioContext: null,
    expectingRawWav: false,
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
        onError: {
          actions: ['handleSetupError'] // todo: implement
        }
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

function App() {
  const sendRef = useRef();
  const stateRef = useRef();
  const [chatHistory, setChatHistory] = useState([]);
  const playQueueRef = useRef([]);
  const isPlayingRef = useRef(false);

  const setupAudio = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);

    const onBufferReceived = (buffer) => {
      if (!stateRef.current.matches('RECORDING')) {
        return;
      }

      const wav_buffer = float32ArrayToWav(buffer, 48000);
      stateRef.current.context.websocket.send(new TextEncoder().encode(`{"type": "wav"}`));
      stateRef.current.context.websocket.send(wav_buffer);
      console.log("Sent wav segment to server");
    }

    const onTalking = () => {
      // will only transition to RECORDING state if in IDLE state
      // otherwise, stay in recording until stop signal
      sendRef.current("START_RECORDING");
    }

    const onSilence = () => {
      if (!stateRef.current.matches('RECORDING')) {
        return;
      }
      // will only transition to GENERATE state if in RECORDING state
      stateRef.current.context.websocket.send(new TextEncoder().encode(`{"type": "end"}`));
      sendRef.current("STOP_RECORDING");
    }

    await audioContext.audioWorklet.addModule("processor.js");
    const recorderNode = new RecorderNode(
      audioContext,
      onBufferReceived,
      onTalking,
      onSilence,
      () => {},
    );

    source.connect(recorderNode);
    recorderNode.connect(audioContext.destination);
    console.log("Audio setup complete");
    return { recorderNode, audioContext };
  }

  const openWebsocket = async (onWebsocketMessage) => {
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
      socket.onmessage = onWebsocketMessage;
      return socket;
    });
  }

  const onWebsocketMessage = async (event) => {
    // this should only ever happen in the generating state
    if (!stateRef.current.matches('GENERATING')) {
      return;
    }

    console.log("onWebsocketMessage");
    if (event.data instanceof Blob){
      const arrayBuffer = await event.data.arrayBuffer();

      // if previous message told us we're expecting a raw wav, send to play queue
      if (stateRef.current.context.expectingRawWav) {
        console.log("Pushing to play queue");
        playQueueRef.current.push(arrayBuffer);
        stateRef.current.context.expectingRawWav = false;
        return;
      }

      // else parse json
      const data = JSON.parse(new TextDecoder().decode(arrayBuffer));
      if (data.type === "wav") {
        console.log("Expecting next message to be wav")
        stateRef.current.context.expectingRawWav = true;
        return;
      } else if (data.type === "text") {
        console.log("Received text message");
        setChatHistory(chatHistory => [...chatHistory, { isUser: false, text: data.value }]);
      } else if (data.type === "transcript") {
        console.log("Received transcript");
        setChatHistory(chatHistory => [...chatHistory, {isUser: true, text: data.value}]);
      }
    }
  }

  // Audio player always runs in the background during GENERATING state
  useEffect(() => {
    const intervalId = setInterval(async () => {
      console.log(1);
      if (stateRef.current.matches('GENERATING') && !isPlayingRef.current) {
        console.log(2);
        if (playQueueRef.current.length === 0) {
          return;
        }
        console.log(3);
        isPlayingRef.current = true;
        console.log(4);
        const arrayBuffer = playQueueRef.current.shift();
        if (arrayBuffer) {
          try {
            console.log("Playing audio");
            const audioBuffer = await stateRef.current.context.audioContext.decodeAudioData(arrayBuffer);
            const source = stateRef.current.context.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(stateRef.current.context.audioContext.destination);
            source.onended = () => {
              console.log("Play ended");
              if (playQueueRef.current.length === 0) {
                console.log("Done");
                isPlayingRef.current = false;
                sendRef.current("GENERATION_COMPLETE");
                return;
              }
            };
            source.start();
            isPlayingRef.current = false;
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
      handleSetupError: (context, event) => {
        console.error('Setup error:', event.data);
      },
      handleResponse: (context, event) => {
        console.log('Handling response:', event.data);
      },
      handleError: (context, event) => {
        console.error('Error occurred:', event.data);
      }
    },
    services: {
      doSetup: async (context) => {
        console.log('Setting up services');

        // Ensure warmup
        await fetch(`https://${backendUrl}/prewarm`);

        // Setup audio if not already setup
        if (!context.recorderNode) {
          const { recorderNode, audioContext } = await setupAudio();
          context.audioContext = audioContext;
          context.recorderNode = recorderNode;
        }
        
        // Create new websocket connection
        const socket = await openWebsocket(onWebsocketMessage);
        context.websocket = socket;

        return Promise.resolve(context);
      },
    }
  });

  sendRef.current = send;
  stateRef.current = state;

  return (
    <div>
      <h1>Voice Chat App!</h1>
      <p>Current State: {state.value}</p>
      {state.value === 'SETUP' && <p>Setting up services...</p>}
      {state.value === 'IDLE' && <p>Speak into mic</p>}
      {state.value === 'RECORDING' && <p>Recording</p>}
      {state.value === 'GENERATING' && <p>Generating response</p>}
      <div className="text-white">
        {chatHistory.map(({ isUser, text }) => (
          <ChatMessage text={text} isUser={isUser} key={text} />
        ))}
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