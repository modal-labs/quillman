"""
Main web application service. Serves the static frontend as well as
API routes for transcription, language model generation and text-to-speech.
"""

from os import pipe
from pathlib import Path
from string import punctuation
import modal
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
    container_idle_timeout=300,
    timeout=600,
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, Request, Response, WebSocket
    from fastapi.responses import Response, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    import numpy as np
    import wave
    import io
    
    web_app = FastAPI()
       
    # serve static files
    # web_app.mount("/", StaticFiles(directory="/assets", html=True))

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
    
    def float32_to_wav(float32_buffer, sample_rate=44100):
        # Convert to int16
        int16_data = (float32_buffer * 32767).astype(np.int16)
        
        # Create an in-memory binary stream
        byte_io = io.BytesIO()
        
        # Create WAV file in the binary stream
        with wave.open(byte_io, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample (16 bits)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(int16_data.tobytes())
        
        # Get the WAV data as bytes
        wav_data = byte_io.getvalue()
        return wav_data

    @web_app.websocket("/pipeline")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()

        # temp: testing pipeline timing
        global pipeline_start_time
        pipeline_start_time= time.time()


        # TEMP: make very simple
        buffer = b""
        try:
            while True:
                data = await websocket.receive_bytes()
                
                if data == b'<END>':
                    # Handle end of transmission
                    if buffer:
                        # Process any remaining data in the buffer
                        float32_buffer = np.frombuffer(buffer, dtype=np.float32)
                        wav_data = float32_to_wav(float32_buffer)
                        await websocket.send_bytes(wav_data)
                    break
                
                buffer += data
                
                # Process as many complete float32 samples as possible
                num_complete_samples = len(buffer) // 4  # 4 bytes per float32
                if num_complete_samples > 0:
                    complete_data = buffer[:num_complete_samples * 4]
                    buffer = buffer[num_complete_samples * 4:]
                    
                    float32_buffer = np.frombuffer(complete_data, dtype=np.float32)
                    wav_data = float32_to_wav(float32_buffer)
                    
                    await websocket.send_bytes(wav_data)
        
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await websocket.close()
        return

        # Step 1: User streams their input in via WebSocket
        async def user_input_stream_gen():
            i = 0
            while True:
                timeprint("websocket.receive_bytes waiting for WAV chunk", i)
                wav_bytes = await websocket.receive_bytes()
                if wav_bytes == b"<END>":
                    timeprint("websocket.receive_bytes received <END> signal")
                    break
                timeprint("websocket.receive_bytes received WAV chunk", i)
                i += 1
                yield wav_bytes

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

        # We now have a single transcript to send to the LLM
        llm_response_stream_gen = zephyr.generate.remote_gen(transcript)
        
        # llm_response_stream_gen will yield words, which we'll want to 
        # accumulate together into sentences for more natural-sounding TTS.
        punctuation = [".", "?", "!", ":", ";", "*"]
        max_words = 5
        def tts_input_stream_acccumulator(text_stream):
            chunk_i = 0
            current_chunk = ""
            for word in text_stream:
                # receives yields from LLM
                timeprint("LLM GENERATION: yielded word", word)

                # TODO: explore why so many empty words are generated

                current_chunk += word + " "

                # yield if we're above max words
                if len(current_chunk.split(" ")) > max_words:
                    # yields sentences to TTS
                    timeprint(f"TTS: starting sentence {chunk_i}:", current_chunk)
                    chunk_i += 1
                    yield current_chunk
                    current_chunk = ""
                    continue

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
        async for wavBytesIO in tts_output_stream_gen:
            # Stream the WAV bytes from the TTS service back to the client
            timeprint(f"TTS: sentence {i} completed, sending to client")
            await websocket.send_bytes(wavBytesIO.getvalue())
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
    