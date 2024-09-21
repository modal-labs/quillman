import asyncio
import time
import os

try:
    import websockets
    import sphn
    import numpy as np
except ImportError:
    print("you need to pip install websockets, sphn, and numpy")

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

    opus_writer = sphn.OpusStreamWriter(sample_rate)
    opus_reader = sphn.OpusStreamReader(sample_rate)

    pcm_data = wav_to_pcm("./test-audio/user_input_chunk1.wav")

    # Append PCM data to OpusStreamWriter in chunks
    for i in range(0, len(pcm_data), frame_size):
        chunk = pcm_data[i:i+frame_size]
        if len(chunk) < frame_size:
            chunk = np.pad(chunk, (0, frame_size - len(chunk)), 'constant')
        opus_writer.append_pcm(chunk)

    last_recv = time.time()
    received_data = False
    silence_cutoff = 3 # seconds

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
                        print("Sent", len(msg), "bytes")

            async def recv_loop():
                nonlocal last_recv, received_data, opus_reader
                while True:
                    # note that opus_writer, on both client and server, send 47 + 53 bytes worth of header immediately 
                    # so the first two recvs we receive are headers and not actual audio data. Useful headers, 
                    # but just keep that in mind when it comes to debugging syncronization issues
                    data = await ws.recv()
                    print("Received", len(data), "bytes")
                    opus_reader.append_bytes(data)
                    last_recv = time.time()
                    received_data = True


            async def timeout_loop():
                while True:
                    await asyncio.sleep(0.1)
                    if received_data and time.time() - last_recv > silence_cutoff:
                        print(f"Server silent for {silence_cutoff}s, closing connection")
                        
                        # will cause a ConnectionClosedError, caught below
                        await ws.close()

            await asyncio.gather(send_loop(), recv_loop(), timeout_loop())
            
    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK):
        print("WebSocket connection closed")
    
    print("Saving output")
    pcm_data = np.array([])
    while True:
        pcm = opus_reader.read_pcm()
        if pcm.shape[0] == 0:
            break
        pcm_data = np.concatenate((pcm_data, pcm), axis=0)
    pcm_data = pcm_data.astype(np.float32)
    sphn.write_wav("./moshi_out.wav", pcm_data, sample_rate)

asyncio.run(main())