# websocket test

import asyncio
import websockets
import json
import sphn
import scipy.io.wavfile
import numpy as np

def read_wav_to_pcm(path: str) -> np.ndarray:
    wav = scipy.io.wavfile.read(path)
    pcm = wav[1].astype(np.float32)
    return pcm

async def main():
    sample_rate: float = 24000
    frame_size: int = 1920

    ## ERIK TODO FOR TOMORROW
    # this client is broken. we want to stream opus to the server as bytes
    # it should echo them back to the client as bytes

    opus_writer = sphn.OpusStreamWriter(sample_rate)
    opus_reader = sphn.OpusStreamReader(sample_rate)
    with open("./test-audio/user_input_chunk1.opus", "rb") as f:
        opus_reader.append_bytes(f.read())

    pcm = opus_reader.read_pcm()
    opus_writer.append_pcm(pcm)

    async with websockets.connect("wss://erik-dunteman--src-prototype-moshi-app-dev.modal.run/ws") as websocket:

        async def send_loop():
            while True:
                await asyncio.sleep(0.001)
                msg = opus_writer.read_bytes()
                await websocket.send(msg)

        async def recv_loop():
            while True:
                data = await websocket.recv()
                print("got data back")

        asyncio.gather(send_loop(), recv_loop())
        
asyncio.run(main())