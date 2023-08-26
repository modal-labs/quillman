"""
Text-to-speech service based on the tortoise-tts library.

The following code is based on code from the https://github.com/metavoicexyz/tortoise-tts-modal-api
repository, which is licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License. You may obtain a
copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import io
from modal import Image, method
from elevenlabs import generate
import pydub
from .common import stub

eleven_image = (
    Image.debian_slim(python_version="3.10.8")  # , requirements_path=req)
    .apt_install("git", "libsndfile-dev", "ffmpeg", "curl")
    .pip_install(
        # TODO: remove all these
        # "torch==2.0.0",
        # "torchvision==0.15.1",
        # "torchaudio==2.0.1",
        "pydub==0.25.1",
        # "transformers==4.25.1",
        "elevenlabs==0.2.24",
        extra_index_url="https://download.pytorch.org/whl/cu117",
    )
)


@stub.cls(
    image=eleven_image,
    # gpu="A10G",
    container_idle_timeout=300,
    timeout=180,
)
class ElevenVoice:
    TONE_FOLDER = "phonesounds"
    VALID_TONES = set(list("#0123456789"))
    def __init__(self):
        self.tone_char_to_filestem = {**{"#": "pound"}, **{str(num): str(num) for num in range(10)}}
        self.tone_char_to_audio_seg = {
            tone_char: pydub.AudioSegment.from_mp3(f"{self.TONE_FOLDER}/{filestem}.mp3")
            for tone_char, filestem in self.tone_char_to_filestem.items()
        }

    def __enter__(self):
        """
        Load the model weights into GPU memory when the container starts.
        """

    @method()
    def speak(self, text, voices=["geralt"]):
        """
        Runs tortoise tts on a given text and voice. Alternatively, a
        web path can be to a target file to be used instead of a voice for
        one-shot synthesis.
        """
        audio_blob = generate(
            text=text,
            api_key="231fb5b69ce57aa9abf2ad11fd7a96b6",
            voice="ZQVy0O9PGQ9D8GMfh8VX",
            model="eleven_monolingual_v1"
        )
        wavdata = io.BytesIO(audio_blob)
        wavdata.seek(0)
        return wavdata


    @method()
    def dialtones(self, tones: str) -> io.BytesIO:
        concat_audio = pydub.AudioSegment.empty()
        for tone in tones:
            if tone not in self.VALID_TONES:
                continue
            concat_audio += self.tone_char_to_audio_seg[tone]
        wavdata = io.BytesIO()
        concat_audio.export(wavdata, format="wav")
        wavdata.seek(0)
        return wavdata

if __name__ == "__main__":
    voice = ElevenVoice()
    # data = voice.dialtones.local("51651239#")
    data = voice.speak.local("Please place a hold on my Chase account")
    with open("benvoice.wav", 'wb') as f:
        f.write(data.read())
