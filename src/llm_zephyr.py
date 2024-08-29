"""
Zephyr 7B (beta) language model, 4-bit quantized for faster inference.

Path to weights provided for illustration purposes only,
please check the license before using for commercial purposes!
"""
import time
from pathlib import Path

import modal

# from .common import app
from .common_proto import app

MODEL_NAME = "TheBloke/zephyr-7B-beta-AWQ"


zephyr_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "autoawq==0.1.8",
        "torch==2.1.2",
    )
)


with zephyr_image.imports():
    from threading import Thread
    from transformers import AutoTokenizer, TextIteratorStreamer
    from awq import AutoAWQForCausalLM


@app.cls(
    image=zephyr_image, 
    gpu="A10G", 
    container_idle_timeout=300,
    timeout=300,
)
class Zephyr:
    def __init__(self):
        print("Initializing zephyr model")

    @modal.build()
    def download_model(self):
        from huggingface_hub import snapshot_download

        snapshot_download(MODEL_NAME)


    @modal.enter()
    def load_model(self):
        t0 = time.time()
        print("Loading AWQ quantized model...")

        self.model = AutoAWQForCausalLM.from_quantized(MODEL_NAME, fuse_layers=False, version="GEMV")

        print(f"Model loaded in {time.time() - t0:.2f}s")

        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)

    @modal.method()
    def prewarm(self):
        # no-op to prewarm LLM model instance
        pass

    @modal.method(is_generator=True)
    async def generate(self, input, history=[]):
        if input == "":
            return

        t0 = time.time()

        messages = [{ "role": "system", "content": "" }]
        for message in history:
            print("Adding history", message)
            messages.append(message) # expects message format { "role": "user", "content": ... }

        messages.append({ "role": "user", "content": input })
        tokenized_chat = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_tensors="pt").cuda()

        generation_kwargs = dict(
            inputs=tokenized_chat,
            streamer=self.streamer,
            do_sample=True,
            temperature=0.9,
            top_p=0.95,
            repetition_penalty=1.2,
            max_new_tokens=1024,
        )

        # Run generation on separate thread to enable response streaming.
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()
        for next_word in self.streamer:
            next_word = next_word.strip()
            if next_word == "":
                # ignore empty words which are sometimes generated
                continue
            yield next_word
        thread.join()
        print(f"Output generated in {time.time() - t0:.2f}s")


# For local testing, run `modal run -q src.llm_zephyr --input "Where is the best sushi in New York?"`
@app.local_entrypoint()
def zephyr_entrypoint(input: str):
    model = Zephyr()
    for val in model.generate.remote_gen(input):
        print(val, end="", flush=True)
