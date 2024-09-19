"""
Main web application service. Serves the static frontend as well as
API routes for transcription, language model generation and text-to-speech.
"""
from pathlib import Path
import modal
import base64

from .xtts import XTTS
from .whisper import Whisper
from .llama import Llama
from .fillers import Fillers
import time

from .common import app

static_path = Path(__file__).with_name("frontend").resolve()

@app.function(
    mounts=[modal.Mount.from_local_dir(static_path, remote_path="/assets")],
    container_idle_timeout=600,
    timeout=600,
    allow_concurrent_inputs=100,
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, Response, WebSocket
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import Response
    from fastapi.staticfiles import StaticFiles
    import json

    # disable caching on static files
    StaticFiles.is_not_modified = lambda self, *args, **kwargs: False

    web_app = FastAPI()

    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Instantiate the inference modules
    whisper = Whisper()
    llama = Llama()
    xtts = XTTS()
    fillers = Fillers()

    @web_app.get("/status")
    async def status():
        """Return the status of each inference module, to provide feedback to the user about the app's readiness."""
        whisper_stats = whisper.prewarm.get_current_stats()
        llama_stats = llama.prewarm.get_current_stats()
        xtts_stats = xtts.prewarm.get_current_stats()
        return {
            "whisper": whisper_stats.num_total_runners > 0
            and whisper_stats.backlog == 0,
            "llama": llama_stats.num_total_runners > 0 and llama_stats.backlog == 0,
            "xtts": xtts_stats.num_total_runners > 0 and xtts_stats.backlog == 0,
        }

    @web_app.get("/prewarm")
    async def prewarm():
        """Prewarm the inference modules, to ensure they're ready to receive requests."""
        prewarm_futures = [
            whisper.prewarm.spawn(),
            llama.prewarm.spawn(),
            xtts.prewarm.spawn(),
            fillers.prewarm.spawn(),
        ]
        for i in prewarm_futures:
            i.get()

        return Response(status_code=200)

    @web_app.websocket("/pipeline")
    async def websocket_endpoint(websocket: WebSocket):
        """A websocket endpoint to generate a single response from a user's input.

        Receive Stages:
        1: User streams their input in via WebSocket. Transcription begins immediately. Multiple transcription chunks may be sent in.
            recv: { "type": "wav", "value": <base64 encoded wav bytes> } -> Wav bytes
        2: User optionally sends in a history of previous messages from the chat session.
            recv: { "type": "history", "value": <history> } -> <history> is a list of OpenAI format chat message history
        3: User sends in the end signal. LLM response generation begins once all transcription chunks are complete.
            recv: { "type": "end" }

        Response Stages:
        4: Pre-synthesized filler audio is selected and sent to the client, to shorten the initial silence.
        5: LLM response generation yields completed sentences. Each sentence is sent to TTS.
        6: TTS yields a sentence at a time. Each sentence is sent back to the client.
            send: { "type": "text", "value": <text> } -> <text> is a text sentence from the LLM
            send: { "type": "wav", "value": <base64 encoded wav bytes> } -> Wav bytes
        7: Once all TTS chunks are sent, the websocket is closed.
        """
        await websocket.accept()

        history = []

        # Receive message stream from client
        async def user_input_stream_gen():
            while True:
                msg_bytes = await websocket.receive_bytes()
                msg = json.loads(msg_bytes.decode())
                if msg["type"] == "end":
                    critical_stage_start_time = time.time()
                    # Request stage complete
                    break
                elif msg["type"] == "history":
                    # we're receiving a history chunk
                    for history_entry in msg["value"]:
                        history.append(history_entry)
                    continue
                elif msg["type"] == "wav":
                    wav_bytes = base64.b64decode(msg["value"])
                    yield wav_bytes
                else:
                    print(
                        f"websocket.receive_bytes received unknown message type: {msg['type']}"
                    )
                    continue

        # Transcribe user input wavs the moment they become available
        transcribe_futures = []
        async for chunk in user_input_stream_gen():
            transcribe_futures.append(whisper.transcribe.spawn(chunk))

        # Await all transcription chunks, since reponse generation
        # requires the full transcript before it can begin
        transcript_chunks = []
        for id in transcribe_futures:
            transcript_chunk = id.get()
            transcript_chunks.append(transcript_chunk)

        # Send the completed transcript back to the client
        transcript = " ".join(transcript_chunks)
        await websocket.send_bytes(
            json.dumps({"type": "transcript", "value": transcript}).encode()
        )

        # While we think, send back filler audio
        sentences = fillers.neighbors.remote(transcript, n=1)
        for sentence in sentences:
            wav_bytesio = fillers.fetch_wav.remote(sentence)
            if wav_bytesio is not None:
                await websocket.send_bytes(
                    json.dumps(
                        {
                            "type": "wav",
                            "value": base64.b64encode(wav_bytesio.getvalue()).decode(
                                "utf-8"
                            ),
                        }
                    ).encode()
                )
                await websocket.send_bytes(
                    json.dumps({"type": "text", "value": sentence}).encode()
                )

        # Send the transcript to the LLM
        llm_response_stream_gen = llama.generate.remote_gen(transcript, history)

        # Accumulate the LLM response stream into sentences
        # for more natural-sounding TTS.
        punctuation = [".", "?", "!", ":", ";", "*"]

        def tts_input_stream_acccumulator(text_stream):
            current_chunk = ""
            for word in text_stream:
                current_chunk += word + " "
                for p in punctuation:
                    if p in word:
                        # yields sentences to TTS
                        yield current_chunk
                        current_chunk = ""
                        break
            # send last chunk
            if current_chunk != "":
                yield current_chunk

        tts_input_stream_gen = tts_input_stream_acccumulator(llm_response_stream_gen)

        # We pass the generator into xtts.speak.map, which returns a generator
        # This allows us to get access to the XTTS futures as they resolve, even if text is still being generated
        tts_output_stream_gen = xtts.speak.map(tts_input_stream_gen)

        async for text, wav_bytesio in tts_output_stream_gen:
            # Send the text string to the client for the chat UI to display
            await websocket.send_bytes(
                json.dumps({"type": "text", "value": text}).encode()
            )

            # Send the wav in two messages: first the json signal, then the actual bytes
            await websocket.send_bytes(
                json.dumps(
                    {
                        "type": "wav",
                        "value": base64.b64encode(wav_bytesio.getvalue()).decode(
                            "utf-8"
                        ),
                    }
                ).encode()
            )

        # All done! Close the websocket.
        await websocket.close()

    # Serve static files, for the frontend
    web_app.mount("/", StaticFiles(directory="/assets", html=True))
    return web_app
