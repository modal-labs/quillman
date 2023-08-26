"""
Main web application service. Serves the static frontend as well as
API routes for transcription, language model generation and text-to-speech.
"""

import json
from pathlib import Path

from modal import Mount, asgi_app

from .common import stub
from .llm_model import AiPhoneModel
from .transcriber import Whisper
from .tts import ElevenVoice

static_path = Path(__file__).with_name("frontend").resolve()

PUNCTUATION = [".", "?", "!", ":", ";", "*"]


@stub.function(
    mounts=[
        Mount.from_local_dir(static_path, remote_path="/assets"),
    ],
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
    llm = AiPhoneModel()
    tts = ElevenVoice()

    @web_app.post("/transcribe")
    async def transcribe(request: Request):
        bytes = await request.body()
        result = transcriber.transcribe_segment.call(bytes)
        return result["text"]

    @web_app.post("/generate")
    async def generate(request: Request):
        body = await request.json()
        # always use ben voice
        tts_enabled = True

        if "noop" in body:
            llm.generate.spawn("")
            # Warm up 3 containers for now.
            if tts_enabled:
                for _ in range(3):
                    tts.speak.spawn("")
            return

        def speak(sentence, is_dialtones=False):
            if tts_enabled:
                print(f"This is sentence: {sentence} and is_dialtones: {is_dialtones}")
                if not is_dialtones:
                    fc = tts.speak.spawn(sentence)
                    return {
                        "type": "audio",
                        "value": fc.object_id,
                    }
                else:
                    print(f"Inside dialtones and is sentence: {sentence} and is_dialtones: {is_dialtones}")
                    fc = tts.dialtones.spawn(sentence)
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
            is_dialtone = False
            for response in llm.generate.call(body["input"], body["history"]):
                print(f"This is llm generate response: {response}")
                segment = response['response']
                is_dialtone = response['should_press_buttons']
                print(f"This is segment: {segment}", flush=True)
                print(f"This is is_dialtone: {is_dialtone}", flush=True)
                yield {"type": "text", "value": segment}
                sentence += segment
                print(f"This is sentence: {sentence}")

                for p in PUNCTUATION:
                    if p in sentence:
                        prev_sentence, new_sentence = sentence.rsplit(p, 1)
                        print(f"The sentence to speak is: {prev_sentence}")
                        yield speak(prev_sentence, is_dialtones=is_dialtone)
                        sentence = new_sentence
                        is_dialtone = is_dialtone

            if sentence:
                print(f"The sentence to speak is: {sentence}")
                yield speak(sentence, is_dialtone)

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
