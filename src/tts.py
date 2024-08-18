"""
Text-to-speech service based on the Coqui TTS library.

The following code is based on the [Tortoise model](https://docs.coqui.ai/en/latest/models/tortoise.html#) from the [Coqui TTS](https://github.com/coqui-ai/TTS)
repository, which is licensed under the Mozilla Public License 2.0 (the "License");
you may not use this file except in compliance with the License. You may obtain a
copy of the License at https://github.com/coqui-ai/TTS/blob/dev/LICENSE.txt.
"""

# https://docs.coqui.ai/en/latest/models/tortoise.html

import io

import modal

# from .common import app
app = modal.App(name="tortoise-tts")

tortoise_image = (
    modal.Image.debian_slim(python_version="3.11.9")
    .apt_install("git")
    .workdir("/app")
    .run_commands("git clone https://github.com/2noise/ChatTTS.git")
    .pip_install("torch", "torchaudio")
)

with tortoise_image.imports():
    import torch
    import torchaudio
    import ChatTTS
    torch._dynamo.config.cache_size_limit = 64
    torch._dynamo.config.suppress_errors = True
    torch.set_float32_matmul_precision('high')

@app.cls(
    image=tortoise_image,
    gpu="A10G",
    container_idle_timeout=300,
    timeout=180,
)
class Tortoise:
    def __init__(self, model_id = "tts_models/en/multi-dataset/tortoise-v2"):
        self.model_id = model_id

    # We can stack the build and enter methods since TTS loads the model and caches it in memory, 
    # so it will work in both build and on container boot
    @modal.build() 
    @modal.enter()
    def load_model(self):
        # """
        # Load the model weights into GPU memory when the container starts.
        # """
        # from TTS.api import TTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # self.tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        import os
        print(os.listdir("./"))

        import ChatTTS


        self.chat = ChatTTS.Chat().to(device)
        self.chat.load_models(compile=False) # Set to True for better performance


    @modal.method()
    def speak(self, text):
        """
        Runs tortoise tts on a given text.
        """
        
        text = text.strip()
        if not text:
            return
        
        # config = {
        #     # "num_autoregressive_samples": 32,  # Increased from default 16
        #     # "diffusion_iterations": 50,        # Increased from default 30
        #     # "temperature": 0.5,                 # Slightly increased from default 0.2
        #     # "length_penalty": 1.0,              # Default value
        #     # "repetition_penalty": 2.5,          # Slightly increased to reduce repetitions
        #     # "top_p": 0.8,                       # Default value
        #     # "cond_free_k": 2.0,                 # Default value
        #     # "diffusion_temperature": 1.0,       # Default value
        # }

        wavs = self.chat.infer([text])
        wav_file = io.BytesIO()
        torchaudio.save(wav_file, torch.from_numpy(wavs[0]), 24000)
        return wav_file.getvalue()
        
        # # do inference and save into an in-memory wav file
        # wav = io.BytesIO()
        # self.tts.tts_to_file(text, file_path=wav, **config)

        # # return wav as a bytes object
        # return wav.getvalue()


@app.local_entrypoint()
def main(text: str):
    tts = Tortoise()
    wav = tts.speak.remote(text)

    with open("output.wav", "wb") as f:
        f.write(wav)
