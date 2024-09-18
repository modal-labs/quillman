"""
Text generation service based on the Llama 3.1 8B Instruct model by Meta.

The model is an [FP8 quantized version by Neural Magic](https://huggingface.co/neuralmagic/Meta-Llama-3.1-8B-Instruct-FP8), which is licensed under the Llama3.1 license.

We use the [VLLM](https://github.com/vllm-project/vllm) library to run the model.
"""
import time
import os

import modal

from .common import app

MODEL_DIR = "/model"
MODEL_NAME = "neuralmagic/Meta-Llama-3.1-8B-Instruct-FP8"
GPU_CONFIG = modal.gpu.A100(size="40GB", count=1)

llama_image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "transformers==4.44.2",
        "vllm==0.6.0",
        "torch==2.4.0",
        "hf_transfer==0.1.8",
        "huggingface_hub==0.24.6",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

@app.cls(
    gpu=GPU_CONFIG,
    timeout=60 * 10,
    container_idle_timeout=60 * 10,
    allow_concurrent_inputs=10,
    image=llama_image,
)
class Llama:
    @modal.build()
    def download_model(self):
        from huggingface_hub import snapshot_download, login
        from transformers.utils import move_cache

        print("Downloading model, this may take a few minutes...")
        os.makedirs(MODEL_DIR, exist_ok=True)
        snapshot_download(
            MODEL_NAME,
            local_dir=MODEL_DIR,
            ignore_patterns=["*.pt", "*.bin"],  # Using safetensors
        )
        move_cache()

    @modal.enter()
    def start_engine(self):
        from vllm.engine.arg_utils import AsyncEngineArgs
        from vllm.engine.async_llm_engine import AsyncLLMEngine
        from transformers import AutoTokenizer
        t0 = time.time()

        engine_args = AsyncEngineArgs(
            model=MODEL_DIR,
            tensor_parallel_size=GPU_CONFIG.count,
            gpu_memory_utilization=0.90,
            enforce_eager=False,  # capture the graph for faster inference, but slower cold starts
            disable_log_stats=True,  # disable logging so we can stream tokens
            disable_log_requests=True,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

        # this can take some time!
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)
        print(f"VLLM engine started in {time.time() - t0:.2f}s")

    @modal.method()
    def prewarm(self):
        # no-op to prewarm model instance
        pass

    @modal.method(is_generator=True)
    async def generate(self, prompt, history=[]):
        from vllm import SamplingParams
        from vllm.utils import random_uuid

        messages = [
            {"role": "system", "content": f"You are a helpful AI assistant. Respond to the human to the best of your ability. Keep it brief."},
        ]

        for history_entry in history:
            # history follows "role" + "content" format so can be used directly
            messages.append(history_entry)

        messages.append({"role": "user", "content": prompt})

        prompts = self.tokenizer.apply_chat_template(messages, tokenize=False)
        sampling_params = SamplingParams(
            temperature=0.75, 
            top_p=0.9, 
            max_tokens=256, 
            repetition_penalty=1.1
        )
        request_id = random_uuid()
        print(f"Request {request_id} generating with prompt:\n{prompts}")
        result_stream = self.engine.generate(prompts, sampling_params, request_id)
        index = 0
        buffer = ""
        header_complete = False
        async for output in result_stream:
            if output.outputs[0].text and "\ufffd" == output.outputs[0].text[-1]:
                # Skip incomplete unicode characters
                continue

            new_text = output.outputs[0].text[index:]
            index = len(output.outputs[0].text)

            # ignore leading <|start_header_id|>assistant<|end_header_id|>
            if not header_complete:
                if new_text == "<|end_header_id|>":
                    header_complete = True
                continue

            buffer += new_text

            # Yield any complete words in the buffer
            while buffer:
                space_index = buffer.find(" ")
                if space_index == -1:
                    break
                
                word = buffer[:space_index + 1]
                yield word.strip()
                
                buffer = buffer[space_index + 1:]

        # Yield any remaining content in the buffer
        if buffer.strip():
            yield buffer.strip()

@app.local_entrypoint()
def main(prompt: str = "Who was Emperor Norton I, and what was his significance in San Francisco's history?"):
    model = Llama()
    for token in model.generate.remote_gen(prompt):
        print(token, end=" ")

