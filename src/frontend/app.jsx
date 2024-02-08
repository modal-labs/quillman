import RecorderNode from "./recorder-node.js";

const { useState, useEffect, useCallback, useRef } = React;

const { createMachine, assign } = XState;
const { useMachine } = XStateReact;

const SILENT_DELAY = 4000; // in milliseconds
const CANCEL_OLD_AUDIO = false; // TODO: set this to true after cancellations don't terminate containers.
const INITIAL_MESSAGE =
  "Hi! I'm a language model running on Modal. Talk to me using your microphone, and remember to turn your speaker volume up!";

const INDICATOR_TYPE = {
  TALKING: "talking",
  SILENT: "silent",
  GENERATING: "generating",
  IDLE: "idle",
};

const MODELS = [
  { id: "zephyr-7b-beta-4bit", label: "Zephyr 7B beta (4-bit)" },
  // { id: "vicuna-13b-4bit", label: "Vicuna 13B (4-bit)" },
  // { id: "alpaca-lora-7b", label: "Alpaca LORA 7B" },
];

const chatMachine = createMachine(
  {
    initial: "botDone",
    context: {
      pendingSegments: 0,
      transcript: "",
      messages: 1,
    },
    states: {
      botGenerating: {
        on: {
          GENERATION_DONE: { target: "botDone", actions: "resetTranscript" },
        },
      },
      botDone: {
        on: {
          TYPING_DONE: {
            target: "userSilent",
            actions: ["resetPendingSegments", "incrementMessages"],
          },
          SEGMENT_RECVD: {
            target: "userTalking",
            actions: [
              "resetPendingSegments",
              "segmentReceive",
              "incrementMessages",
            ],
          },
        },
      },
      userTalking: {
        on: {
          SILENCE: { target: "userSilent" },
          SEGMENT_RECVD: { actions: "segmentReceive" },
          TRANSCRIPT_RECVD: { actions: "transcriptReceive" },
        },
      },
      userSilent: {
        on: {
          SOUND: { target: "userTalking" },
          SEGMENT_RECVD: { actions: "segmentReceive" },
          TRANSCRIPT_RECVD: { actions: "transcriptReceive" },
        },
        after: [
          {
            delay: SILENT_DELAY,
            target: "botGenerating",
            actions: "incrementMessages",
            cond: "canGenerate",
          },
          {
            delay: SILENT_DELAY,
            target: "userSilent",
          },
        ],
      },
    },
  },
  {
    actions: {
      segmentReceive: assign({
        pendingSegments: (context) => context.pendingSegments + 1,
      }),
      transcriptReceive: assign({
        pendingSegments: (context) => context.pendingSegments - 1,
        transcript: (context, event) => {
          console.log(context, event);
          return context.transcript + event.transcript;
        },
      }),
      resetPendingSegments: assign({ pendingSegments: 0 }),
      incrementMessages: assign({
        messages: (context) => context.messages + 1,
      }),
      resetTranscript: assign({ transcript: "" }),
    },
    guards: {
      canGenerate: (context) => {
        console.log(context);
        return context.pendingSegments === 0 && context.transcript.length > 0;
      },
    },
  }
);

function Sidebar({
  selected,
  isTortoiseOn,
  isMicOn,
  setIsMicOn,
  setIsTortoiseOn,
  onModelSelect,
}) {
  return (
    <nav className="bg-zinc-900 w-[400px] flex flex-col h-full gap-2 p-2 text-gray-100 ">
      <h1 className="text-4xl font-semibold text-center text-zinc-200 ml-auto mr-auto flex gap-2 items-center justify-center h-20">
        QuiLLMan
        <span className="bg-yellow-300 text-yellow-900 py-0.5 px-1.5 text-xs rounded-md uppercase">
          Plus
        </span>
      </h1>
      <div className="flex flex-row justify-evenly mb-4">
        <button
          className="flex items-center justify-center w-8 h-8 min-w-8 min-h-8 fill-zinc-300 hover:fill-zinc-50"
          onClick={() => setIsMicOn(!isMicOn)}
        >
          {isMicOn ? <MicOnIcon /> : <MicOffIcon />}
        </button>
        <div className="group flex relative">
          <button
            className="flex items-center justify-center w-8 h-8 min-w-8 min-h-8 fill-zinc-300 hover:fill-zinc-50"
            onClick={() => setIsTortoiseOn(!isTortoiseOn)}
          >
            {isTortoiseOn ? <FaceIcon /> : <BotIcon />}
          </button>

          <span
            className="group-hover:opacity-100 transition-opacity bg-zinc-900 px-1 text-sm text-zinc-100 rounded-md absolute left-1/2 
    -translate-x-1/2 translate-y-1/2 w-fit opacity-0 m-2 mx-auto"
          >
            {isTortoiseOn ? "TTS (natural; slow)" : "TTS (system; fast)"}
          </span>
        </div>
      </div>
      {MODELS.map(({ id, label }) => (
        <button
          key={id}
          className={
            "py-2 items-center justify-center rounded-md cursor-pointer border border-white/20 hover:bg-white/10 hover:text-zinc-200 " +
            (id == selected
              ? "bg-opacity-10 bg-primary ring-1 ring-primary text-zinc-200"
              : "text-zinc-400 ")
          }
          onClick={() => onModelSelect(id)}
        >
          {label}
        </button>
      ))}
      <button
        className="py-2 items-center justify-center rounded-md cursor-pointer border border-white/20 pointer-events-none"
        onClick={() => onModelSelect(id)}
        disabled
      >
        More coming soon!
      </button>
      <a
        className="items-center flex justify-center mt-auto"
        href="https://modal.com"
        target="_blank"
        rel="noopener noreferrer"
      >
        <footer className="flex flex-row items-center w-42 p-1 mb-6 rounded shadow-lg">
          <span className="p-1 text-md">
            <strong>built with</strong>
          </span>
          <img className="h-12 w-24" src="./modal-logo.svg"></img>
        </footer>
      </a>
    </nav>
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

function FaceIcon() {
  return (
    <svg
      className="w-full h-full"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 512 512"
    >
      {/*! Font Awesome Pro 6.4.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license (Commercial License) Copyright 2023 Fonticons, Inc.*/}
      <path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM164.1 325.5C182 346.2 212.6 368 256 368s74-21.8 91.9-42.5c5.8-6.7 15.9-7.4 22.6-1.6s7.4 15.9 1.6 22.6C349.8 372.1 311.1 400 256 400s-93.8-27.9-116.1-53.5c-5.8-6.7-5.1-16.8 1.6-22.6s16.8-5.1 22.6 1.6zM144.4 208a32 32 0 1 1 64 0 32 32 0 1 1 -64 0zm192-32a32 32 0 1 1 0 64 32 32 0 1 1 0-64z" />
    </svg>
  );
}

function MicOnIcon() {
  return (
    <svg
      className="w-full h-full"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 640 512"
    >
      {/*! Font Awesome Pro 6.4.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license (Commercial License) Copyright 2023 Fonticons, Inc.*/}
      <path
        d="M192 0C139 0 96 43 96 96V256c0 53 43 96 96 96s96-43 96-96V96c0-53-43-96-96-96zM64 216c0-13.3-10.7-24-24-24s-24 10.7-24 24v40c0 89.1 66.2 162.7 152 174.4V464H120c-13.3 0-24 10.7-24 24s10.7 24 24 24h72 72c13.3 0 24-10.7 24-24s-10.7-24-24-24H216V430.4c85.8-11.7 152-85.3 152-174.4V216c0-13.3-10.7-24-24-24s-24 10.7-24 24v40c0 70.7-57.3 128-128 128s-128-57.3-128-128V216z"
        transform="translate(128, 0)"
      />
    </svg>
  );
}

function MicOffIcon() {
  return (
    <svg
      className="w-full h-full"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 640 512"
    >
      {/*! Font Awesome Pro 6.4.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license (Commercial License) Copyright 2023 Fonticons, Inc.*/}
      <path d="M38.8 5.1C28.4-3.1 13.3-1.2 5.1 9.2S-1.2 34.7 9.2 42.9l592 464c10.4 8.2 25.5 6.3 33.7-4.1s6.3-25.5-4.1-33.7L472.1 344.7c15.2-26 23.9-56.3 23.9-88.7V216c0-13.3-10.7-24-24-24s-24 10.7-24 24v40c0 21.2-5.1 41.1-14.2 58.7L416 300.8V96c0-53-43-96-96-96s-96 43-96 96v54.3L38.8 5.1zM344 430.4c20.4-2.8 39.7-9.1 57.3-18.2l-43.1-33.9C346.1 382 333.3 384 320 384c-70.7 0-128-57.3-128-128v-8.7L144.7 210c-.5 1.9-.7 3.9-.7 6v40c0 89.1 66.2 162.7 152 174.4V464H248c-13.3 0-24 10.7-24 24s10.7 24 24 24h72 72c13.3 0 24-10.7 24-24s-10.7-24-24-24H344V430.4z" />
    </svg>
  );
}

function TalkingSpinner({ isUser }) {
  return (
    <div className={"flex items-center justify-center"}>
      <div
        className={
          "talking [&>span]:" + (isUser ? "bg-yellow-500" : "bg-primary")
        }
      >
        {" "}
        <span /> <span /> <span />{" "}
      </div>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="scale-[0.2] w-6 h-6 flex items-center justify-center">
      <div className="lds-spinner [&>div:after]:bg-zinc-200">
        {[...Array(12)].map((_, i) => (
          <div key={i}></div>
        ))}
      </div>
    </div>
  );
}

function ChatMessage({ text, isUser, indicator }) {
  return (
    <div className="w-full">
      <div className="text-base gap-4 p-4 flex m-auto">
        <div className="flex flex-col gap-2">
          <div
            className={
              "flex items-center justify-center w-8 h-8 min-w-8 mih-h-8" +
              (isUser ? " fill-yellow-500" : " fill-primary")
            }
          >
            {isUser ? <UserIcon /> : <BotIcon />}
          </div>
          {indicator == INDICATOR_TYPE.TALKING && (
            <TalkingSpinner isUser={isUser} />
          )}
          {indicator == INDICATOR_TYPE.GENERATING && <LoadingSpinner />}
        </div>
        <div>
          <div
            className={
              "whitespace-pre-wrap rounded-[16px] px-3 py-1.5 max-w-[600px] bg-zinc-800 border " +
              (!text
                ? " pulse text-sm text-zinc-300 border-gray-600"
                : isUser
                ? " text-zinc-100 border-yellow-500"
                : " text-zinc-100 border-primary")
            }
          >
            {text ||
              (isUser
                ? "Speak into your microphone to talk to the bot..."
                : "Bot is typing...")}
          </div>
        </div>
      </div>
    </div>
  );
}

class PlayQueue {
  constructor(audioContext, onChange) {
    this.call_ids = [];
    this.audioContext = audioContext;
    this._onChange = onChange;
    this._isProcessing = false;
    this._indicators = {};
  }

  async add(item) {
    this.call_ids.push(item);
    this.play();
  }

  _updateState(idx, indicator) {
    this._indicators[idx] = indicator;
    this._onChange(this._indicators);
  }

  _onEnd(idx) {
    this._updateState(idx, INDICATOR_TYPE.IDLE);
    this._isProcessing = false;
    this.play();
  }

  async play() {
    if (this._isProcessing || this.call_ids.length === 0) {
      return;
    }

    this._isProcessing = true;

    const [payload, idx, isTts] = this.call_ids.shift();
    this._updateState(idx, INDICATOR_TYPE.GENERATING);

    if (!isTts) {
      const audio = new SpeechSynthesisUtterance(payload);
      audio.onend = () => this._onEnd(idx);
      this._updateState(idx, INDICATOR_TYPE.TALKING);
      window.speechSynthesis.speak(audio);
      return;
    }

    const call_id = payload;
    console.log("Fetching audio for call", call_id, idx);

    let response;
    let success = false;
    while (true) {
      response = await fetch(`/audio/${call_id}`);
      if (response.status === 202) {
        continue;
      } else if (response.status === 204) {
        console.error("No audio found for call: " + call_id);
        break;
      } else if (!response.ok) {
        console.error("Error occurred fetching audio: " + response.status);
      } else {
        success = true;
        break;
      }
    }

    if (!success) {
      this._onEnd(idx);
      return;
    }

    const arrayBuffer = await response.arrayBuffer();
    const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);

    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.audioContext.destination);

    source.onended = () => this._onEnd(idx);

    this._updateState(idx, INDICATOR_TYPE.TALKING);
    source.start();
  }

  clear() {
    for (const [call_id, _, isTts] of this.call_ids) {
      if (isTts) {
        fetch(`/audio/${call_id}`, { method: "DELETE" });
      }
    }
    this.call_ids = [];
  }
}

async function fetchTranscript(buffer) {
  const blob = new Blob([buffer], { type: "audio/float32" });

  const response = await fetch("/transcribe", {
    method: "POST",
    body: blob,
    headers: { "Content-Type": "audio/float32" },
  });

  if (!response.ok) {
    console.error("Error occurred during transcription: " + response.status);
  }

  return await response.json();
}

async function* fetchGeneration(noop, input, history, isTortoiseOn) {
  const body = noop
    ? { noop: true, tts: isTortoiseOn }
    : { input, history, tts: isTortoiseOn };

  const response = await fetch("/generate", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    console.error("Error occurred during submission: " + response.status);
  }

  if (noop) {
    return;
  }

  const readableStream = response.body;
  const decoder = new TextDecoder();

  const reader = readableStream.getReader();

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    for (let message of decoder.decode(value).split("\x1e")) {
      if (message.length === 0) {
        continue;
      }

      const { type, value: payload } = JSON.parse(message);

      yield { type, payload };
    }
  }

  reader.releaseLock();
}

function App() {
  const [history, setHistory] = useState([]);
  const [fullMessage, setFullMessage] = useState(INITIAL_MESSAGE);
  const [typedMessage, setTypedMessage] = useState("");
  const [model, setModel] = useState(MODELS[0].id);
  const [botIndicators, setBotIndicators] = useState({});
  const [state, send, service] = useMachine(chatMachine);
  const [isMicOn, setIsMicOn] = useState(true);
  const [isTortoiseOn, setIsTortoiseOn] = useState(false);
  const recorderNodeRef = useRef(null);
  const playQueueRef = useRef(null);

  useEffect(() => {
    const subscription = service.subscribe((state, event) => {
      console.log("Transitioned to state:", state.value, state.context);

      if (event && event.type == "TRANSCRIPT_RECVD") {
        setFullMessage(
          (m) => m + (m ? event.transcript : event.transcript.trimStart())
        );
      }
    });

    return subscription.unsubscribe;
  }, [service]);

  const generateResponse = useCallback(
    async (noop, input = "") => {
      if (!noop) {
        recorderNodeRef.current.stop();
      }

      console.log("Generating response", input, history);

      let firstAudioRecvd = false;
      for await (let { type, payload } of fetchGeneration(
        noop,
        input,
        history.slice(1),
        isTortoiseOn
      )) {
        if (type === "text") {
          setFullMessage((m) => m + payload);
        } else if (type === "audio") {
          if (!firstAudioRecvd && CANCEL_OLD_AUDIO) {
            playQueueRef.current.clear();
            firstAudioRecvd = true;
          }
          playQueueRef.current.add([payload, history.length + 1, true]);
        } else if (type === "sentence") {
          playQueueRef.current.add([payload, history.length + 1, false]);
        }
      }

      if (!isTortoiseOn && playQueueRef.current) {
        while (
          playQueueRef.current.call_ids.length ||
          playQueueRef.current._isProcessing
        ) {
          await new Promise((r) => setTimeout(r, 100));
        }
      }
      console.log("Finished generating response");

      if (!noop) {
        recorderNodeRef.current.start();
        send("GENERATION_DONE");
      }
    },
    [history, isTortoiseOn]
  );

  useEffect(() => {
    const transition = state.context.messages > history.length + 1;

    if (transition && state.matches("botGenerating")) {
      generateResponse(/* noop = */ false, fullMessage);
    }

    if (transition) {
      setHistory((h) => [...h, fullMessage]);
      setFullMessage("");
      setTypedMessage("");
    }
  }, [state, history, fullMessage]);

  const onSegmentRecv = useCallback(
    async (buffer) => {
      if (buffer.length) {
        send("SEGMENT_RECVD");
      }
      // TODO: these can get reordered
      const data = await fetchTranscript(buffer);
      if (buffer.length) {
        send({ type: "TRANSCRIPT_RECVD", transcript: data });
      }
    },
    [history]
  );

  async function onMount() {
    // Warm up GPU functions.
    onSegmentRecv(new Float32Array());
    generateResponse(/* noop = */ true);

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    const context = new AudioContext();

    const source = context.createMediaStreamSource(stream);

    await context.audioWorklet.addModule("processor.js");
    const recorderNode = new RecorderNode(
      context,
      onSegmentRecv,
      () => send("SILENCE"),
      () => send("SOUND")
    );
    recorderNodeRef.current = recorderNode;

    source.connect(recorderNode);
    recorderNode.connect(context.destination);

    playQueueRef.current = new PlayQueue(context, setBotIndicators);
  }

  useEffect(() => {
    onMount();
  }, []);

  const tick = useCallback(() => {
    if (!recorderNodeRef.current) {
      return;
    }

    if (typedMessage.length < fullMessage.length) {
      const n = 1; // Math.round(Math.random() * 3) + 3;
      setTypedMessage(fullMessage.substring(0, typedMessage.length + n));

      if (typedMessage.length + n == fullMessage.length) {
        send("TYPING_DONE");
      }
    }
  }, [typedMessage, fullMessage]);

  useEffect(() => {
    const intervalId = setInterval(tick, 20);
    return () => clearInterval(intervalId);
  }, [tick]);

  const onModelSelect = (id) => {
    setModel(id);
  };

  useEffect(() => {
    if (recorderNodeRef.current) {
      console.log("Mic", isMicOn);

      if (isMicOn) {
        recorderNodeRef.current.start();
      } else {
        recorderNodeRef.current.stop();
      }
    }
  }, [isMicOn]);

  useEffect(() => {
    if (playQueueRef.current && !isTortoiseOn) {
      console.log("Canceling future audio calls");
      playQueueRef.current.clear();
    }
  }, [isTortoiseOn]);

  const isUserLast = history.length % 2 == 1;
  let userIndicator = INDICATOR_TYPE.IDLE;

  if (isUserLast) {
    userIndicator = state.matches("userTalking")
      ? INDICATOR_TYPE.TALKING
      : INDICATOR_TYPE.SILENT;
  }

  useEffect(() => {
    console.log("Bot indicator changed", botIndicators);
  }, [botIndicators]);

  return (
    <div className="min-w-full min-h-screen screen">
      <div className="w-full h-screen flex">
        <Sidebar
          selected={model}
          onModelSelect={onModelSelect}
          isMicOn={isMicOn}
          isTortoiseOn={isTortoiseOn}
          setIsMicOn={setIsMicOn}
          setIsTortoiseOn={setIsTortoiseOn}
        />
        <main className="bg-zinc-800 w-full flex flex-col items-center gap-3 pt-6 overflow-auto">
          {history.map((msg, i) => (
            <ChatMessage
              key={i}
              text={msg}
              isUser={i % 2 == 1}
              indicator={i % 2 == 0 && botIndicators[i]}
            />
          ))}
          <ChatMessage
            text={typedMessage}
            isUser={isUserLast}
            indicator={
              isUserLast ? userIndicator : botIndicators[history.length]
            }
          />
        </main>
      </div>
    </div>
  );
}

const container = document.getElementById("react");
ReactDOM.createRoot(container).render(<App />);
