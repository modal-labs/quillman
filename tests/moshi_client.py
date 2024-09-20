import asyncio
import websockets
import sphn
import numpy as np

async def main():
    sample_rate: float = 24000
    frame_size: int = 1920

    # Initialize OpusStreamWriter
    opus_writer = sphn.OpusStreamWriter(sample_rate)

    # Read audio file using sphn.read
    audio_path = "./test-audio/user_input_chunk1.wav"  # Replace with your audio file path
    pcm_data, file_sample_rate = sphn.read(audio_path)

    # Resample if necessary
    if file_sample_rate != sample_rate:
        pcm_data = sphn.resample(pcm_data, src_sample_rate=file_sample_rate, dst_sample_rate=sample_rate)

    # Ensure the PCM data is in the correct shape (mono)
    if len(pcm_data.shape) > 1:
        pcm_data = pcm_data[:, 0]  # Take the first channel if stereo

    # Convert to float32 if not already
    pcm_data = pcm_data.astype(np.float32)

    # Append PCM data to OpusStreamWriter in chunks
    for i in range(0, len(pcm_data), frame_size):
        chunk = pcm_data[i:i+frame_size]
        if len(chunk) < frame_size:
            chunk = np.pad(chunk, (0, frame_size - len(chunk)), 'constant')
        opus_writer.append_pcm(chunk)

    try:
        async with websockets.connect("wss://erik-dunteman--src-prototype-moshi-app-dev.modal.run/ws") as ws:
            async def send_loop():
                while True:
                    await asyncio.sleep(0.001)
                    msg = opus_writer.read_bytes()
                    if len(msg) > 0:
                        print("sending", len(msg))
                        await ws.send(msg) 

            async def recv_loop():
                i = 0
                while True:
                    data = await ws.recv()
                    print(i, "got data back", len(data))
                    i += 1

            await asyncio.gather(send_loop(), recv_loop())
    except websockets.exceptions.ConnectionClosedError:
        print("WebSocket connection closed")
        exit(0)

asyncio.run(main())