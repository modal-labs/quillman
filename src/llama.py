"""
Text generation service based on the Llama 3.1 8B Instruct model.

The model is based on the [Meta-Llama](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct) model, which is licensed under the Llama3.1 license.

Pulling the model weights from HuggingFace requires Meta org approval.
Follow these steps to optain pull access:
- Go to https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct
- Scroll through the "LLAMA 3.1 COMMUNITY LICENSE AGREEMENT"
- Fill out the form and submit
- Acquire a HuggingFace API token from https://huggingface.co/settings/tokens
- Set that token as a Modal secret with the name "huggingface-key" at https://modal.com/secrets, using the variable name "HF_TOKEN"

Access is usually granted within an hour or two.

We use the [VLLM](https://github.com/vllm-project/vllm) library to run the model.
"""

import time
import os

import modal

from .common import app

MODEL_DIR = "/model"

# Llama 3.1 requires an org approval, usually granted within a few hours
MODEL_NAME = "meta-llama/Meta-Llama-3.1-8B-Instruct"
GPU_CONFIG = modal.gpu.A100(size="40GB", count=1)

def download_model_to_image(model_dir, model_name):
    from huggingface_hub import snapshot_download, login
    from transformers.utils import move_cache
    print(os.environ)

    login(os.environ["HF_TOKEN"])

    os.makedirs(model_dir, exist_ok=True)

    snapshot_download(
        model_name,
        local_dir=model_dir,
        ignore_patterns=["*.pt", "*.bin"],  # Using safetensors
    )
    move_cache()


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
    secrets=[modal.Secret.from_name("huggingface-key")],
)
class Llama:
    @modal.build()
    def download_model(self):
        # pip freeze
        try: 
            from pip._internal.operations import freeze
        except ImportError: # pip < 10.0
            from pip.operations import freeze

        pkgs = freeze.freeze()
        for pkg in pkgs: 
            print(pkg)

        from huggingface_hub import snapshot_download, login
        from transformers.utils import move_cache
        login(os.environ["HF_TOKEN"])

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
        t0 = time.time()

        engine_args = AsyncEngineArgs(
            model=MODEL_DIR,
            tensor_parallel_size=GPU_CONFIG.count,
            gpu_memory_utilization=0.90,
            enforce_eager=False,  # capture the graph for faster inference, but slower cold starts
            disable_log_stats=True,  # disable logging so we can stream tokens
            disable_log_requests=True,
        )

        # this can take some time!
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)
        print(f"VLLM engine started in {time.time() - t0:.2f}s")

    @modal.method()
    def prewarm(self):
        # no-op to prewarm model instance
        pass

    @modal.method(is_generator=True)
    async def generate(self, input, history=[]):
        from vllm import SamplingParams
        from vllm.utils import random_uuid

        stop_token = "<|END|>"
        stop_tokens = [stop_token, "Human:"] # prevent model from generating a response to itself
        system_prompt = f"You are a helpful AI assistant. Respond to the human to the best of your ability. Keep it brief.. When you have completed your response, end it with the token {stop_token}. For example: Human: What's the capital of France? Assistant: The capital of France is Paris.{stop_token}"

        sampling_params = SamplingParams(
            temperature=0.75,
            max_tokens=128,
            repetition_penalty=1.1,
            stop=stop_tokens,
            include_stop_str_in_output=False,
        )

        # prepend system message to history
        history.insert(0, { "role": "system", "content": system_prompt })

        # Convert chat history to a single string
        prompt = ""
        for message in history:
            role = message["role"]
            content = message["content"]
            if role == "system":
                prompt += f"System: {content}\n"
            elif role == "user":
                prompt += f"Human: {content}\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n"

        # Add the current user input
        prompt += f"Human: {input}\n"
        prompt += "Assistant: "

        request_id = random_uuid()
        print(f"Request {request_id} generating with prompt:{prompt}")
        result_stream = self.engine.generate(
            prompt,
            sampling_params,
            request_id,
        )

        index = 0
        buffer = ""
        async for output in result_stream:
            if output.outputs[0].text and "\ufffd" == output.outputs[0].text[-1]:
                # Skip incomplete unicode characters
                continue

            new_text = output.outputs[0].text[index:]
            buffer += new_text
            index = len(output.outputs[0].text)

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

