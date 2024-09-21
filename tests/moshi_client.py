import asyncio
from curses import nonl
from io import BytesIO
import time
import websockets
import sphn
import numpy as np

def wav_to_pcm(wav_path: str, sample_rate: int = 24000, frame_size: int = 1920):
    pcm_data, file_sample_rate = sphn.read(wav_path)

    # Resample if necessary
    if file_sample_rate != sample_rate:
        pcm_data = sphn.resample(pcm_data, src_sample_rate=file_sample_rate, dst_sample_rate=sample_rate)

    # Ensure the PCM data is in the correct shape (mono)
    if len(pcm_data.shape) > 1:
        pcm_data = np.mean(pcm_data, axis=0)  # Convert stereo to mono by averaging channels

    # Convert to float32 if not already
    pcm_data = pcm_data.astype(np.float32)

    return pcm_data

async def main():
    sample_rate: float = 24000
    frame_size: int = 1920

    # Initialize OpusStreamWriter
    opus_writer = sphn.OpusStreamWriter(sample_rate)

    pcm_data = wav_to_pcm("./test-audio/user_input_chunk1.wav")

    # Append PCM data to OpusStreamWriter in chunks
    for i in range(0, len(pcm_data), frame_size):
        chunk = pcm_data[i:i+frame_size]
        if len(chunk) < frame_size:
            chunk = np.pad(chunk, (0, frame_size - len(chunk)), 'constant')
        opus_writer.append_pcm(chunk)

    all_opus_data = []

    try:
        async with websockets.connect(
            "wss://erik-dunteman--quillman-moshi-app-dev.modal.run/ws",
            open_timeout=600,
        ) as ws:
            async def send_loop():
                while True:
                    await asyncio.sleep(0.001)
                    msg = opus_writer.read_bytes()
                    if len(msg) > 0:
                        await ws.send(msg) 
                        print(f"sent {len(msg)} bytes")

            async def recv_loop():
                while True:
                    # note that opus_writer, on both client and server, send 47 + 53 bytes worth of header immediately 
                    # so the first two recvs we receive are headers and not actual audio data. Useful headers, 
                    # but just keep that in mind when it comes to debugging syncronization issues
                    data = await ws.recv()
                    print(f"got {len(data)} bytes")
                    for b in data:
                        all_opus_data.append(b)

            async def save_loop():
                i = 0
                nonlocal all_opus_data
                while True:
                    await asyncio.sleep(5)
                    if len(all_opus_data) > 0:
                        print("saving")
                    
                        with open(f"./user_output_chunk{i}.opus", "wb") as f:
                            f.write(bytearray(all_opus_data))

                        all_opus_data = []

                        i += 1

                    

            await asyncio.gather(send_loop(), recv_loop(), save_loop())
    except websockets.exceptions.ConnectionClosedError:
        print("WebSocket connection closed")

asyncio.run(main())#