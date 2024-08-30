"""
Speech-to-text transcriptiong service based on OpenAI Whisper V3 large.
"""

import time
import modal
from .common import app

cuda_version = "12.4.0"  # should be no greater than host CUDA version
flavor = "devel"  #  includes full CUDA toolkit
os = "ubuntu22.04"
tag = f"{cuda_version}-{flavor}-{os}"

# We need flash-attn to speed up inference so we use a custom CUDA image with nvcc installed
whisper_image = (
    modal.Image.from_registry(f"nvidia/cuda:{tag}", add_python="3.11")
    .apt_install("git", "ffmpeg")
    .pip_install(
        "transformers", "accelerate", "wheel", "ninja", "torch"
    )
    .pip_install(
        "flash-attn", extra_options="--no-build-isolation",
    )
)

with whisper_image.imports():
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

@app.cls(
    gpu="A10G",
    image=whisper_image,
    container_idle_timeout=600,
    timeout=300,
)
class Whisper:
    def __init__(self):
        print("Initializing whisper transcriber")
        pass

    @modal.build()
    @modal.enter()
    def load_model(self):
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        model_id = "openai/whisper-large-v3"
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True, attn_implementation="flash_attention_2"
        )
        
        model.to(device)
        processor = AutoProcessor.from_pretrained(model_id)
    
        # store our whisper pipeline for later use
        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=torch_dtype,
            device=device,
        )

    @modal.method()
    def prewarm(self):
        # no-op to prewarm whisper model instance
        pass

    @modal.method()
    def transcribe(
        self,
        audio_data: bytes,
    ):
        t0 = time.time()
        result = self.pipe(audio_data)
        print(f"Transcribed in {time.time() - t0:.2f}s")
        return result["text"]


# For local testing, run `modal run -q src.whisper
@app.local_entrypoint()
def test_whisper():
    import os
    from pathlib import Path
    whisper = Whisper()

    # We have three sample audio files in the test-audio folder that we'll transcribe
    files = os.listdir("tests/test-audio")
    files.sort()
    for file in files:
        file = "tests/test-audio" / Path(file)
        with open(file, "rb") as f:
            audio_data = f.read()
        result = whisper.transcribe.remote(audio_data)
        print(result)