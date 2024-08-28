"""
Main web application service. Serves the static frontend as well as
API routes for transcription, language model generation and text-to-speech.
"""

from os import pipe
from pathlib import Path
from string import punctuation
import modal
import modal.container_process
import time
from .xtts import XTTS
from .whisper import Whisper
from .llm_zephyr import Zephyr

from .common_proto import app

pipeline_start_time = time.time()
def timeprint(*args):
    print(f"{time.time() - pipeline_start_time}s", *args)

static_path = Path(__file__).with_name("frontend").resolve()

@app.function(
    # mounts=[modal.Mount.from_local_dir(static_path, remote_path="/assets")],
    container_idle_timeout=600,
    timeout=600,
    max_concurrency=1,
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, Response, WebSocket
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import Response
    from fastapi.staticfiles import StaticFiles
    import fastapi

    import numpy as np
    import json
    
    web_app = FastAPI()

    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
       
    # serve static files
    # web_app.mount("/", StaticFiles(directory="/assets", html=True))

    # other Cls-based services on my app
    whisper = Whisper()
    zephyr = Zephyr()
    xtts = XTTS()

    @web_app.get("/status")
    async def status():
        whisper_stats = whisper.prewarm.get_current_stats()
        zephyr_stats = zephyr.prewarm.get_current_stats()
        xtts_stats = xtts.prewarm.get_current_stats()
        return {
            "whisper": whisper_stats.num_total_runners > 0 and whisper_stats.backlog == 0,
            "zephyr": zephyr_stats.num_total_runners > 0 and zephyr_stats.backlog == 0,
            "xtts": xtts_stats.num_total_runners > 0 and xtts_stats.backlog == 0,
        }

    @web_app.get("/prewarm")
    async def prewarm():
        prewarm_futures = [
            whisper.prewarm.spawn(),
            zephyr.prewarm.spawn(),
            xtts.prewarm.spawn(),
        ]
        for i in prewarm_futures:
            i.get()

        return Response(status_code=200)

    @web_app.websocket("/pipeline")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()

        # websocket endpoint is a two-way stream of json messages   
        # { "type": "history", "value": <history> }
        # { "type": "end" }
        # { "type": "text", "value": <text> }
        # { "type": "wav" }
        #   in the case of type "wav", the following message will be the raw wav bytes rather than json

        # temp: testing pipeline timing
        global pipeline_start_time
        pipeline_start_time= time.time()

        # Step 1: User streams their input in via WebSocket
        async def user_input_stream_gen():
            i = 0
            while True:
                timeprint("web socket.receive_bytes waiting for WAV chunk", i)
                msg_bytes = await websocket.receive_bytes()
                msg = json.loads(msg_bytes.decode())
                if msg["type"] == "end":
                    timeprint("websocket.receive_bytes received END signal")
                    break
                elif msg["type"] == "history":
                    # we're receiving a history chunk
                    history = msg["value"]
                    timeprint("websocket.receive_bytes received history chunk", history)
                    continue
                elif msg["type"] == "wav":
                    # first message is the json signal that we're receiving a wav
                    # the next message will be the wav bytes itself
                    wav_bytes = await websocket.receive_bytes()
                    timeprint("websocket.receive_bytes received WAV chunk", i)
                    i += 1
                    yield wav_bytes
                else:
                    print(f"websocket.receive_bytes received unknown message type: {msg['type']}")
                    continue

        # We parallel transcribe user input chunks
        transcribe_futures = []
        i = 0
        async for chunk in user_input_stream_gen():
            timeprint("TRANSCRIPTION: starting WAV chunk", i)
            i += 1
            # the moment the chunk arrives, we start transcribing it
            transcribe_futures.append(whisper.transcribe.spawn(chunk))
        
        # We await all transcription chunks
        transcript_chunks = []
        i = 0
        for id in transcribe_futures:
            timeprint("TRANSCRIPTION: awaiting chunk", i)
            i += 1
            transcript_chunk = id.get()
            transcript_chunks.append(transcript_chunk)
        transcript = " ".join(transcript_chunks)
        timeprint("TRANSCRIPTION: complete", transcript)
        await websocket.send_bytes(json.dumps({
            "type": "transcript", 
            "value": transcript
        }).encode())

        # We now have a single transcript to send to the LLM
        llm_response_stream_gen = zephyr.generate.remote_gen(transcript)
        
        # llm_response_stream_gen will yield words, which we'll want to 
        # accumulate together into sentences for more natural-sounding TTS.
        punctuation = [".", "?", "!", ":", ";", "*"]
        def tts_input_stream_acccumulator(text_stream):
            chunk_i = 0
            current_chunk = ""
            for word in text_stream:
                # receives yields from LLM
                current_chunk += word + " "

                # yield if we're at punctuation
                for p in punctuation:
                    if p in word:
                        # yields sentences to TTS
                        timeprint(f"TTS: starting sentence {chunk_i}:", current_chunk)
                        chunk_i += 1
                        yield current_chunk
                        current_chunk = ""
                        break
            # last chunk
            if current_chunk != "":
                timeprint(f"TTS: last sentence {chunk_i}:", current_chunk)
                yield current_chunk
        
        # Stream the word-by-word response from the LLM into the accumulator
        tts_input_stream_gen = tts_input_stream_acccumulator(llm_response_stream_gen)

        # Stream the sentences from the accumulator into the TTS service
        tts_output_stream_gen = xtts.speak.map(tts_input_stream_gen)
        i = 0
        async for text, wav_bytesio in tts_output_stream_gen:
            # Stream the WAV bytes from the TTS service back to the client
            timeprint(f"TTS: sentence {i} completed, sending to client")
            await websocket.send_bytes(json.dumps({
                "type": "text", 
                "value": text
            }).encode())

            # send the wav bytes, first the signal, then the actual bytes
            await websocket.send_bytes(json.dumps({
                "type": "wav"
            }).encode())
            await websocket.send_bytes(wav_bytesio.getvalue())

            timeprint(f"TTS: sentence {i} sent to client")
            i += 1

        timeprint("PIPELINE COMPLETE")
        await websocket.close()
        
    return web_app



## TODO: 
# current pipeline takes 8.4sec from end of user speech to first LLM token
# bottlenecks
#   - LLM response generation takes 2sec to output the first sentence.
#   - TTS 2.5sec on that first sentence
    