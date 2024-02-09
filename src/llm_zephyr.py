"""
Zephyr 7B (beta) language model, 4-bit quantized for faster inference.

Path to weights provided for illustration purposes only,
please check the license before using for commercial purposes!
"""
import time
from pathlib import Path

from modal import Image, build, enter, method

from .common import stub

MODEL_NAME = "TheBloke/zephyr-7B-beta-AWQ"


zephyr_image = (
    Image.debian_slim(python_version="3.11")
    .pip_install(
        "autoawq==0.1.8",
        "torch==2.1.2",
    )
)


with zephyr_image.imports():
    from threading import Thread
    from transformers import AutoTokenizer, TextIteratorStreamer
    from awq import AutoAWQForCausalLM


@stub.cls(image=zephyr_image, gpu="T4", container_idle_timeout=300)
class Zephyr:
    @build()
    def download_model(self):
        from huggingface_hub import snapshot_download

        snapshot_download(MODEL_NAME)


    @enter()
    def load_model(self):
        t0 = time.time()
        print("Loading AWQ quantized model...")

        self.model = AutoAWQForCausalLM.from_quantized(MODEL_NAME, fuse_layers=False, version="GEMV")

        print(f"Model loaded in {time.time() - t0:.2f}s")

        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)


    @method()
    async def generate(self, input, history=[]):
        if input == "":
            return

        t0 = time.time()

        assert len(history) % 2 == 0, "History must be an even number of messages"

        messages = [{ "role": "system", "content": "" }]
        for i in range(0, len(history), 2):
            messages.append({ "role": "user", "content": history[i] })
            messages.append({ "role": "user", "content": history[i+1] })

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
        for new_text in self.streamer:
            yield new_text
        thread.join()

        print(f"Output generated in {time.time() - t0:.2f}s")


# For local testing, run `modal run -q src.llm_zephyr --input "Where is the best sushi in New York?"`
@stub.local_entrypoint()
def main(input: str):
    model = Zephyr()
    for val in model.generate.remote_gen(input):
        print(val, end="", flush=True)
