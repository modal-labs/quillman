const { useRef, useEffect, useState } = React;

const baseURL = "" // points to whatever is serving this app (eg your -dev.modal.run for modal serve, or .modal.run for modal deploy)

const App = () => {
  const socketRef = useRef(null);

  // get permission to use microphone
  const [hasPermission, setHasPermission] = useState(false);
  useEffect(() => {
    (async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setHasPermission(true);
    })();
  }, []);

  // start recording
  const startRecording = () => {
    const recorder = new Recorder({
      encoderPath: "https://cdn.jsdelivr.net/npm/opus-recorder@latest/dist/encoderWorker.min.js",
      streamPages: true,
      encoderApplication: 2049, // todo investigate if needed
      encoderFrameSize: 80, // milliseconds, equal to 1920 samples at 24000 Hz
      encoderSampleRate: 24000,  // 24000 on server
      maxFramesPerPage: 1, // reduce to decrease chunk size, at cost of higher processing overhead
      numberOfChannels: 1,
    });

    recorder.ondataavailable = async (arrayBuffer) => {
      // Handle encoded audio data
      // console.log("Received Opus data", arrayBuffer);
      if (socketRef.current) {
        if (socketRef.current.readyState !== WebSocket.OPEN) {
          console.log("Socket not open, dropping audio");
          return;
        }
        console.log("stream up")
        await socketRef.current.send(arrayBuffer);
      }
    };

    // Start recording when needed
    recorder.start().then(() => console.log("Recording started"));
  };

  // open websocket connection
  useEffect(() => {
    const endpoint = "wss://erik-dunteman--quillman-moshi-app-dev.modal.run/ws"; // todo make dynamic
    console.log("Connecting to", endpoint);
    const socket = new WebSocket(endpoint);
    socketRef.current = socket;

    socket.onopen = () => {
      startRecording();
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
        console.log("Received text data", text);
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
    <div className="app absolute h-screen w-screen flex text-white">
      <div className="flex w-full">
        <div className="w-1/6">
          <Sidebar amplitude={0.03} />
        </div>
        <div className="w-5/6 flex-grow overflow-auto flex-col items-center p-3 px-6">
          <h1 className="text-2xl">Chat</h1>
            <ChatMessage content={"hello nerd"} role={"assistant"} key={"hello nerd"} />
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

const Sidebar = ({amplitude}) => {
  return (
    <div className="bg-zinc-800 fixed w-1/6 top-0 bottom-0 flex flex-col items-center p-4">
      <h1 className="text-3xl">QuiLLMan</h1>
      <div className="flex flex-col gap-2 w-full mt-8 text-md">
        <h2 className="text-xl">Service Status</h2>
        <div className="flex justify-between items-center">
          <p>Moshi</p>
          <div className="text-red-500 text-xl">●</div>
        </div>
      </div>
      <div className="mt-8 w-full">
        <MicLevels micAmplitude={amplitude} micThreshold={0.1} isRecordingState={true} />
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

const MicLevels = ({ micAmplitude }) => {
  const maxAmplitude = 0.2; // for scaling

  return (
    <div className="w-full max-w-md mx-auto space-y-2">
      <h1  className="text-xl">Mic Settings</h1>
      <label className="block text-sm font-medium text-gray-300">Mic Level</label>
      <div className={`relative h-4 rounded-full overflow-hidden bg-zinc-600`}>
        <div 
          className={`absolute top-0 left-0 h-full transition-all duration-100 ease-out bg-zinc-200`}
          style={{ width: `${(micAmplitude / maxAmplitude) * 100}%` }}
        ></div>
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