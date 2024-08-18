"""
Main web application service. Serves the static frontend as well as
API routes for transcription, language model generation and text-to-speech.
"""

import json
from pathlib import Path

from modal import Mount, asgi_app

from .common import app
from .llm_zephyr import Zephyr
from .transcriber import Whisper
from .tts import Tortoise

static_path = Path(__file__).with_name("frontend").resolve()

PUNCTUATION = [".", "?", "!", ":", ";", "*"]


@app.function(
    mounts=[Mount.from_local_dir(static_path, remote_path="/assets")],
    container_idle_timeout=300,
    timeout=600,
)
@asgi_app()
def web():
    from fastapi import FastAPI, Request
    from fastapi.responses import Response, StreamingResponse
    from fastapi.staticfiles import StaticFiles

    web_app = FastAPI()
    transcriber = Whisper()
    llm = Zephyr()
    tts = Tortoise()

    @web_app.post("/transcribe")
    async def transcribe(request: Request):
        bytes = await request.body()
        result = transcriber.transcribe_segment.remote(bytes)
        return result["text"]

    @web_app.post("/generate")
    async def generate(request: Request):
        body = await request.json()
        tts_enabled = body["tts"]

        if "noop" in body:
            llm.generate.spawn("")
            # Warm up 3 containers for now.
            if tts_enabled:
                for _ in range(3):
                    tts.speak.spawn("")
            return

        def speak(sentence):
            if tts_enabled:
                fc = tts.speak.spawn(sentence)
                return {
                    "type": "audio",
                    "value": fc.object_id,
                }
            else:
                return {
                    "type": "sentence",
                    "value": sentence,
                }

        def gen():
            sentence = ""

            for segment in llm.generate.remote_gen(body["input"], body["history"]):
                yield {"type": "text", "value": segment}
                sentence += segment

                for p in PUNCTUATION:
                    if p in sentence:
                        prev_sentence, new_sentence = sentence.rsplit(p, 1)
                        yield speak(prev_sentence)
                        sentence = new_sentence

            if sentence:
                yield speak(sentence)

        def gen_serialized():
            for i in gen():
                yield json.dumps(i) + "\x1e"

        return StreamingResponse(
            gen_serialized(),
            media_type="text/event-stream",
        )

    @web_app.get("/audio/{call_id}")
    async def get_audio(call_id: str):
        from modal.functions import FunctionCall

        function_call = FunctionCall.from_id(call_id)
        try:
            result = function_call.get(timeout=30)
        except TimeoutError:
            return Response(status_code=202)

        if result is None:
            return Response(status_code=204)

        return StreamingResponse(result, media_type="audio/wav")

    @web_app.delete("/audio/{call_id}")
    async def cancel_audio(call_id: str):
        from modal.functions import FunctionCall

        print("Cancelling", call_id)
        function_call = FunctionCall.from_id(call_id)
        function_call.cancel()

    web_app.mount("/", StaticFiles(directory="/assets", html=True))
    return web_app
