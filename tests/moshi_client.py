import asyncio
import sys
import time

try:
    import sounddevice as sd
    import websockets
    import sphn
    import numpy as np
except ImportError:
    print("you need to run `pip install websockets sphn numpy sounddevice`")

# Update this
endpoint = "wss://erik-dunteman--quillman-moshi-app-dev.modal.run/ws"

async def run_pipeline(opus_writer, opus_reader):
    last_recv = time.time()
    received_data = False
    silence_cutoff = 3 # seconds

    try:
        async with websockets.connect(
            endpoint,
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

# helper functions
def wav_to_pcm(wav_path: str, sample_rate: int = 24000, frame_size: int = 1920):
    pcm_data, file_sample_rate = sphn.read(wav_path)
    if file_sample_rate != sample_rate:
        pcm_data = sphn.resample(pcm_data, src_sample_rate=file_sample_rate, dst_sample_rate=sample_rate)
    if len(pcm_data.shape) > 1:
        pcm_data = np.mean(pcm_data, axis=0)
    pcm_data = pcm_data.astype(np.float32)
    return pcm_data

def pcm_from_opus_reader(opus_reader):
    pcm_data = np.array([])
    while True:
        pcm = opus_reader.read_pcm()
        if pcm.shape[0] == 0:
            break
        pcm_data = np.concatenate((pcm_data, pcm), axis=0)
    pcm_data = pcm_data.astype(np.float32)
    return pcm_data

def get_user_mic_input(opus_writer, sample_rate, frame_size):
    import sounddevice as sd
    channels = 1
    def on_audio_input(in_data, frames, time, status):
        assert in_data.shape == (frame_size, channels), in_data.shape
        opus_writer.append_pcm(in_data[:, 0])
    in_stream = sd.InputStream(
        samplerate=sample_rate,
        channels=channels,
        blocksize=frame_size,
        callback=on_audio_input,
    )
    # record for 10 seconds
    with in_stream:
        in_stream.start()
        for i in range(5):
            print(f"Recording for {5-i}s")
            time.sleep(1)
        in_stream.stop()
        print("Recording complete. Awaiting model response.")

def play_audio(pcm_data, sample_rate):  
    import sounddevice as sd
    sd.play(pcm_data, sample_rate)
    sd.wait()

def get_demo_audio(opus_writer, sample_rate, frame_size):
    demo_path = "./test-audio/user_input_chunk1.wav"
    pcm_data = wav_to_pcm(demo_path)
    for i in range(0, len(pcm_data), frame_size):
        chunk = pcm_data[i:i+frame_size]
        if len(chunk) < frame_size:
            chunk = np.pad(chunk, (0, frame_size - len(chunk)), 'constant')
        opus_writer.append_pcm(chunk)

async def main():
    args = sys.argv[1:]

    sample_rate: float = 24000
    frame_size: int = 1920

    interractive = False
    if len(args) > 0:
        if args[0] == "interractive":
            interractive = True

    opus_writer = sphn.OpusStreamWriter(sample_rate)
    opus_reader = sphn.OpusStreamReader(sample_rate)

    # Load up opus_writer with audio data    
    if interractive:
        print("Running in interractive mode.")
        get_user_mic_input(opus_writer, sample_rate, frame_size)
        await run_pipeline(opus_writer, opus_reader)
        pcm_data = pcm_from_opus_reader(opus_reader)
        play_audio(pcm_data, sample_rate)
    else:
        print("Using demo audio.")
        print("Run `python moshi_client.py interractive` to use interractive mode instead.")
        get_demo_audio(opus_writer, sample_rate, frame_size)
        print("Saving output")
        pcm_data = pcm_from_opus_reader(opus_reader)
        sphn.write_wav("/tmp/moshi_out.wav", pcm_data, sample_rate)
        print("Saved output to /tmp/moshi_out.wav")

asyncio.run(main())