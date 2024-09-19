import modal
import time

from .common import app


image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "moshi",
        "huggingface_hub",
        "hf_transfer",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

with image.imports():
    from huggingface_hub import hf_hub_download
    import torch
    from moshi.models import loaders, LMGen
    import sentencepiece

@app.cls(
    image=image,
    gpu="A10G",
    container_idle_timeout=60,
    timeout=60,
)
class Moshi:
    @modal.build()
    def download_model(self):
        hf_hub_download(loaders.DEFAULT_REPO, loaders.MOSHI_NAME)
        hf_hub_download(loaders.DEFAULT_REPO, loaders.MIMI_NAME)
        hf_hub_download(loaders.DEFAULT_REPO, loaders.TEXT_TOKENIZER_NAME)

    @modal.enter()
    def enter(self):
        device = "cuda" if torch.cuda.is_available() else "cpu"

        mimi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MIMI_NAME)
        self.mimi = loaders.get_mimi(mimi_weight, device=device)
        self.mimi.set_num_codebooks(8)
        self.frame_size = int(self.mimi.sample_rate / self.mimi.frame_rate)
        print("Sample rate", self.mimi.sample_rate)

        moshi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MOSHI_NAME)
        self.moshi = loaders.get_moshi_lm(moshi_weight, device=device)
        self.lm_gen = LMGen(self.moshi) # can add temp here

        self.mimi.streaming_forever(1)
        self.lm_gen.streaming_forever(1)

        tokenizer_config = hf_hub_download(loaders.DEFAULT_REPO, loaders.TEXT_TOKENIZER_NAME)
        self.text_tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_config)

        # Warmup them GPUs
        for chunk in range(4):
            chunk = torch.zeros(1, 1, self.frame_size, dtype=torch.float32, device=device)
            codes = self.mimi.encode(chunk)
            for c in range(codes.shape[-1]):
                tokens = self.lm_gen.step(codes[:, :, c: c + 1])
                if tokens is None:
                    continue
                _ = self.mimi.decode(tokens[:, 1:])
        torch.cuda.synchronize()

    @modal.method()
    def generate(self, prompt):
        return prompt
    

@app.local_entrypoint()
def test_moshi(prompt: str = "What is the capital of France?"):
    moshi = Moshi()
    print(moshi.generate.remote(prompt))