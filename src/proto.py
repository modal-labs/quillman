"""
Main web application service. Serves the static frontend as well as
API routes for transcription, language model generation and text-to-speech.
"""

from pathlib import Path
from string import punctuation
import modal
import time
from .xtts import XTTS
from .whisper import Whisper
from .llm_zephyr import Zephyr

from .common_proto import app

# constants
# LLM_TPS = 60

# @app.cls(
#     container_idle_timeout=300,
#     timeout = 180,
#     concurrency_limit=5,
# )
# class LLM:
#     @modal.enter()
#     def load_model(self):
#         print("Loading LLM model")
#         time.sleep(3)
#         print("LLM model loaded")

#     @modal.method()
#     def prewarm(self):
#         # no-op to prewarm LLM model instance
#         pass

#     @modal.method(is_generator=True)
#     def generate(self, text):
#         # text is the output of whisper
        
#         # simulate llm with response streaming
#         for word in text.split(" "):
#             # Why is the final word an empty string here?
#             print(f"Yielding word from llm.generate.remote_gen: |{word}|")
#             time.sleep(1/LLM_TPS)
#             yield word

@app.function( 
    container_idle_timeout=300,
    timeout = 180,
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, Request, Response, WebSocket
    from fastapi.responses import Response, StreamingResponse
    from fastapi.staticfiles import StaticFiles

    web_app = FastAPI()
    whisper = Whisper()
    zephyr = Zephyr()
    xtts = XTTS()

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

        # Step 1: User streams their input in via WebSocket
        async def user_input_stream_gen():
            print("Receiving user WAV input stream...")
            while True:
                wav_bytes = await websocket.receive_bytes()
                if wav_bytes == b"<END>":
                    print("Received end of stream")
                    break
                print("Received WAV chunk")
                yield wav_bytes

        # We parallel transcribe user input chunks
        transcribe_futures = []
        async for chunk in user_input_stream_gen():
            # the moment the chunk arrives, we start transcribing it
            transcribe_futures.append(whisper.transcribe.spawn(chunk))
        
        # We await all transcription chunks
        transcript_chunks = []
        for i in transcribe_futures:
            transcript_chunk = i.get()
            transcript_chunks.append(transcript_chunk)
        transcript = " ".join(transcript_chunks)
        print("Transcript Complete: ", transcript)

        # We now have a single transcript to send to the LLM
        llm_response_stream_gen = zephyr.generate.remote_gen(transcript)
        
        # llm_response_stream_gen will yield words, which we'll want to 
        # accumulate together into sentences for more natural-sounding TTS.
        punctuation = [".", "?", "!", ":", ";", "*"]
        def tts_input_stream_acccumulator(text_stream):
            current_chunk = ""
            for word in text_stream:
                current_chunk += word + " "
                for p in punctuation:
                    if p in word:
                        print("Sentence from LLM ready for TTS: ", current_chunk)
                        yield current_chunk
                        current_chunk = ""
                        break
            # last chunk
            if current_chunk != "":
                yield current_chunk
        
        # Stream the word-by-word response from the LLM into the accumulator
        tts_input_stream_gen = tts_input_stream_acccumulator(llm_response_stream_gen)

        # Stream the sentences from the accumulator into the TTS service
        tts_output_stream_gen = xtts.speak.map(tts_input_stream_gen)
        async for wavBytesIO in tts_output_stream_gen:
            # Stream the WAV bytes from the TTS service back to the client
            print("TTS sentence completed")
            await websocket.send_bytes(wavBytesIO.getvalue())

        print("Pipeline completed, all bytes sent, closing websocket")
        await websocket.close()
    return web_app


@app.local_entrypoint()
def main():
    print("hello!")
    # import sounddevice as sd
    # import numpy as np
    # from scipy.io import wavfile

    # print("Starting dev script")
    # user_input = user_input_generator()
    # whisper = Whisper()
    # llm = LLM()
    # tts = XTTS()

    # # ensure warm instances of everything
    # prewarm_ids = []
    # prewarm_ids.append(whisper.prewarm.spawn())
    # prewarm_ids.append(llm.prewarm.spawn())
    # prewarm_ids.append(tts.prewarm.spawn())
    # for i in prewarm_ids:
    #     i.get()

    # # parallel whisper chunks
    # transcipt_chunks = whisper.transcribe.map(user_input)
    # transcript = " ".join(list(transcipt_chunks)) # await all

    # global user_finish_time
    # print(f"Time since end of user speech to TRANSCRIPTION: {time.time() - user_finish_time}s")

    # # single llm response, streamed back
    # llm_response_stream = llm.generate.remote_gen(transcript)

    # # accumulate text stream into larger chunks split by punctuation, since TTS needs slightly longer chunks to sound natural
    # punctuation = [".", "?", "!", ":", ";", "*"]
    # def chunk_generator(text_stream):
    #     current_chunk = ""
    #     i = 0
    #     for word in text_stream:
    #         if i == 0:
    #             print(f"Time since end of user speech to FIRST LLM TOKEN: {time.time() - user_finish_time}s")
    #         i += 1
    #         current_chunk += word + " "
    #         for p in punctuation:
    #             if p in word:
    #                 yield current_chunk
    #                 current_chunk = ""
    #                 break
        
    #     # last chunk
    #     if current_chunk != "":
    #         yield current_chunk

    # chunk_input = chunk_generator(llm_response_stream)
    # tts_chunks = tts.speak.map(chunk_input)

    # i = 0
    # for chunk in tts_chunks:
    #     if i == 0:
    #         print(f"Time since end of user speech to FIRST TTS CHUNK: {time.time() - user_finish_time}s")

    #     # play WAV
    #     sample_rate, data = wavfile.read(chunk)
    #     sd.play(data, sample_rate)
    #     sd.wait()

    #     with open(f"output_{i}.wav", "wb") as f:
    #         f.write(chunk.getvalue())
    
    #     i += 1
    