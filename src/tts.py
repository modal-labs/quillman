"""
Text-to-speech service based on the ChatTTS library.

The following code is based on the [ChatTTS model](https://github.com/2noise/ChatTTS) repository, 
which is licensed under the GNU AFFERO GENERAL PUBLIC LICENSE (the "License");
The License requires that any derivative work must be fully open source and under the same license.
You may obtain a copy of the License at https://github.com/2noise/ChatTTS/blob/main/LICENSE.
"""

import io
import modal
from .common import app

tts_image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .workdir("/app")
    .pip_install("git+https://github.com/2noise/ChatTTS.git@51ec0c784c2795b257d7a6b64274e7a36186b731")
    .pip_install("soundfile")
)

with tts_image.imports():
    import torch
    import torchaudio
    import ChatTTS

@app.cls(
    image=tts_image,
    gpu="A10G",
    container_idle_timeout=300,
    timeout=180,
)
class TTS:
    def __init__(self, voice = "male"):

        # "voice" translates to a torch seed, which affects the timbre of the voice
        # we generated all voices seed 0-100, and these were the highest quality
        voice_seeds = {
            "female": 28,
            "male": 34,
            "male_alt_1": 43,
        }

        print(f"Using voice {voice} with seed {voice_seeds[voice]}")
        self.voice_seed = voice_seeds[voice]

    # We can stack the build and enter methods since TTS loads the model and caches it in memory, 
    # so it will work in both build and on container boot
    @modal.build() 
    @modal.enter()
    def load_model(self):
        # """
        # Load the model weights into GPU memory when the container starts.
        # """
        import ChatTTS
        
        self.chat = ChatTTS.Chat()
        self.chat.load(compile=False) # Set to True for better performance

        # uses torch seed for deterministic speaker
        torch.manual_seed(self.voice_seed)
        self.rand_spk = self.chat.sample_random_speaker()

    @modal.method()
    def speak(self, text, temperature=0.18, top_p=0.9, top_k=20):
        """
        Runs tortoise tts on a given text.
        """
        
        text = text.strip()
        if not text:
            return

        params_infer_code = ChatTTS.Chat.InferCodeParams(
            spk_emb = self.rand_spk,
            temperature = temperature,
            top_P = top_p,
            top_K = top_k,
        )


        params_refine_text = ChatTTS.Chat.RefineTextParams(
            prompt='[oral_8][laugh_2][break_2]', # expressive and fun voice
        )

        wavs = self.chat.infer(text, skip_refine_text=True, params_infer_code=params_infer_code, params_refine_text=params_refine_text)
        
        # Save into an in-memory wav file
        wav_file = io.BytesIO()
        torchaudio.save(wav_file, torch.from_numpy(wavs[0]).unsqueeze(0), 24000, format="wav", backend="soundfile")

        # # return wav as a file object
        return wav_file


@app.local_entrypoint()
def tts_entrypoint(text: str):
    tts = TTS()
    wav = tts.speak.remote(text)
    with open(f"output.wav", "wb") as f:
        f.write(wav.getvalue())