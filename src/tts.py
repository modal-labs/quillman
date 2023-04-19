"""
Text-to-speech service based on the tortoise-tts library.

The following code is based on code from the https://github.com/metavoicexyz/tortoise-tts-modal-api
repository, which is licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License. You may obtain a
copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import io
import tempfile

from modal import Image, method

from .common import stub


def download_models():
    from tortoise.api import MODELS_DIR, TextToSpeech

    tts = TextToSpeech(models_dir=MODELS_DIR)
    tts.get_random_conditioning_latents()


tortoise_image = (
    Image.debian_slim(python_version="3.10.8")  # , requirements_path=req)
    .apt_install("git", "libsndfile-dev", "ffmpeg", "curl")
    .pip_install(
        "torch==2.0.0",
        "torchvision==0.15.1",
        "torchaudio==2.0.1",
        "pydub==0.25.1",
        "transformers==4.25.1",
        extra_index_url="https://download.pytorch.org/whl/cu117",
    )
    .pip_install("git+https://github.com/metavoicexyz/tortoise-tts")
    .run_function(download_models)
)


@stub.cls(
    image=tortoise_image,
    gpu="A10G",
    container_idle_timeout=300,
    timeout=180,
)
class Tortoise:
    def __enter__(self):
        """
        Load the model weights into GPU memory when the container starts.
        """
        from tortoise.api import MODELS_DIR, TextToSpeech
        from tortoise.utils.audio import load_audio, load_voices

        self.load_voices = load_voices
        self.load_audio = load_audio
        self.tts = TextToSpeech(models_dir=MODELS_DIR)
        self.tts.get_random_conditioning_latents()

    def process_synthesis_result(self, result):
        """
        Converts a audio torch tensor to a binary blob.
        """
        import pydub
        import torchaudio

        with tempfile.NamedTemporaryFile() as converted_wav_tmp:
            torchaudio.save(
                converted_wav_tmp.name + ".wav",
                result,
                24000,
            )
            wav = io.BytesIO()
            _ = pydub.AudioSegment.from_file(
                converted_wav_tmp.name + ".wav", format="wav"
            ).export(wav, format="wav")

        return wav

    @method()
    def speak(self, text, voices=["geralt"]):
        """
        Runs tortoise tts on a given text and voice. Alternatively, a
        web path can be to a target file to be used instead of a voice for
        one-shot synthesis.
        """

        text = text.strip()
        if not text:
            return

        CANDIDATES = 1  # NOTE: this code only works for one candidate.
        CVVP_AMOUNT = 0.0
        SEED = None
        PRESET = "fast"

        voice_samples, conditioning_latents = self.load_voices(voices)

        gen, _ = self.tts.tts_with_preset(
            text,
            k=CANDIDATES,
            voice_samples=voice_samples,
            conditioning_latents=conditioning_latents,
            preset=PRESET,
            use_deterministic_seed=SEED,
            return_deterministic_state=True,
            cvvp_amount=CVVP_AMOUNT,
        )

        wav = self.process_synthesis_result(gen.squeeze(0).cpu())

        return wav
