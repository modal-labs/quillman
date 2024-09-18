"""This file is a test script for end-to-end testing the generation pipeline,
mimicking the actions a user would take on the frontend.

It is intended to call to a dev endpoint, set up through `modal serve src.app`.
"""
import time
import asyncio
import websockets
import os
import requests
import subprocess
import sys
import base64
import wave
import json
from pathlib import Path

workspace = subprocess.run(
    ["modal", "profile", "current"], check=True, capture_output=True, text=True
).stdout.splitlines()[0]

endpoint = f"{workspace}--quillman-web-dev.modal.run"

# We have three sample audio files in the test-audio folder that we'll transcribe
files = os.listdir(Path(__file__).parent / "test-audio")
files.sort()

# we're simulating a user speaking into a microphone
user_finish_time = None

def user_input_generator():
    for wav in files:
        wav = Path(__file__).parent / "test-audio" / wav
        
        # sleep for duration of wav file to simulate user speaking
        duration = wave.open(wav.as_posix(), "rb").getnframes() / wave.open(wav.as_posix(), "rb").getframerate()
        print(f"Simulating user speaking for {duration:.2f} seconds")
        time.sleep(duration)

        with open(wav, "rb") as f:
            yield f.read()

    # used for understanding time of pipeline
    print("User finished speaking, waiting...")
    global user_finish_time
    user_finish_time = time.time()


async def main():

    # Step 1: GET /prewarm endpoint
    print("Prewarming models...")
    for i in range(5):  # retry up to 5 times
        try:
            response = requests.get(f"https://{endpoint}/prewarm")
            response.raise_for_status()
            print("Prewarm request successful")
            break
        except requests.exceptions.RequestException as e:
            wait_time = 2**i  # Exponential backoff: 1s, 2s, 4s, 8s, 16s
            print(f"Request failed ({e}), retrying in {wait_time} seconds...")
            time.sleep(wait_time)
    else:
        print("Max retries exceeded")
        return 1

    # Step 2: WebSocket connection to /pipeline endpoint
    try:
        async with websockets.connect(f"wss://{endpoint}/pipeline") as websocket:
            print("WebSocket connection established")

            for wav in user_input_generator():
                s = time.time()

                await websocket.send(
                    json.dumps(
                        {"type": "wav", "value": base64.b64encode(wav).decode("utf-8")}
                    ).encode()
                )

            history = [
                {"role": "user", "content": "Hello, how are you?"},
                {
                    "role": "assistant",
                    "content": "I'm doing well, thank you for asking!",
                },
            ]
            await websocket.send(
                json.dumps({"type": "history", "value": history}).encode()
            )
            await websocket.send(
                json.dumps(
                    {
                        "type": "end",
                    }
                ).encode()
            )

            print("Waiting for responses...")

            # first response after <END> will be the transcript
            msg_bytes = await websocket.recv()
            msg = json.loads(msg_bytes.decode())
            if msg["type"] != "transcript":
                return
            transcript = msg["value"]
            print(f"Transcript: {transcript}")

            i = 0
            # following responses are in alternating pairs: text, wav
            while True:
                msg_bytes = await websocket.recv()
                msg = json.loads(msg_bytes.decode())
                if msg["type"] == "text":
                    text_response = msg["value"]

                elif msg["type"] == "wav":
                    wav_response = base64.b64decode(msg["value"])
                    if i == 0:
                        print(
                            f"Time since end of user speech to FIRST TTS CHUNK: {time.time() - user_finish_time}s"
                        )

                    with open(f"/tmp/output_{i}.wav", "wb") as f:
                        f.write(wav_response)

                    i += 1

    except websockets.exceptions.WebSocketException:
        pass

    print("Done, output audios saved to /tmp/output_*.wav")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
