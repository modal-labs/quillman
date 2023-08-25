"""
Vicuna 13B language model, 4-bit quantized for faster inference.
Adapted from https://github.com/thisserand/FastChat.git

Path to weights provided for illustration purposes only,
please check the license before using for commercial purposes!
"""
import time
from pathlib import Path

from modal import Image, method

from .common import stub

MODEL_NAME = "anon8231489123/vicuna-13b-GPTQ-4bit-128g"


def download_model():
    from huggingface_hub import snapshot_download

    # Match what FastChat expects
    # https://github.com/thisserand/FastChat/blob/4a57c928a906705404eae06f7a44b4da45828487/download-model.py#L203
    output_folder = f"{'_'.join(MODEL_NAME.split('/')[-2:])}"

    snapshot_download(
        local_dir=Path("/FastChat", "models", output_folder),
        repo_id=MODEL_NAME,
    )


stub.vicuna_image = (
    Image.from_dockerhub(
        "nvidia/cuda:12.2.0-devel-ubuntu20.04",
        setup_dockerfile_commands=[
            "RUN apt-get update",
            "RUN apt-get install -y python3 python3-pip python-is-python3",
        ],
    )
    .apt_install("git", "gcc", "build-essential")
    .run_commands(
        "git clone https://github.com/thisserand/FastChat.git",
        "cd FastChat && pip install -e .",
    )
    .run_commands(
        # FastChat hard-codes a path for GPTQ, so this needs to be cloned inside repositories.
        "git clone https://github.com/oobabooga/GPTQ-for-LLaMa.git -b cuda /FastChat/repositories/GPTQ-for-LLaMa",
        "cd /FastChat/repositories/GPTQ-for-LLaMa && python setup_cuda.py install",
        gpu="any",
    )
    .run_function(download_model)
)

""

if stub.is_inside(stub.vicuna_image):
    t0 = time.time()
    import os
    import warnings

    warnings.filterwarnings(
        "ignore", category=UserWarning, message="TypedStorage is deprecated"
    )

    # This version of FastChat hard-codes a relative path for the model ("./model"),
    # making this necessary :(
    os.chdir("/FastChat")
    from fastchat.conversation import SeparatorStyle, conv_templates
    from fastchat.serve.cli import generate_stream
    from fastchat.serve.load_gptq_model import load_quantized
    from transformers import AutoTokenizer


@stub.cls(image=stub.vicuna_image, gpu="A10G", container_idle_timeout=300)
class Vicuna:
    def __enter__(self):
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

        print("Loading GPTQ quantized model...")
        model = load_quantized(MODEL_NAME)
        model.cuda()

        self.model = model
        self.tokenizer = tokenizer
        print(f"Model loaded in {time.time() - t0:.2f}s")

    @method()
    async def generate(self, input, history=[]):
        if input == "":
            return

        t0 = time.time()

        conv = conv_templates["v1"].copy()

        assert len(history) % 2 == 0, "History must be an even number of messages"

        for i in range(0, len(history), 2):
            conv.append_message(conv.roles[0], history[i])
            conv.append_message(conv.roles[1], history[i + 1])

        conv.append_message(conv.roles[0], input)
        conv.append_message(conv.roles[1], None)
        prompt = conv.get_prompt()

        params = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "temperature": 0.7,
            "max_new_tokens": 512,
            "stop": conv.sep if conv.sep_style == SeparatorStyle.SINGLE else conv.sep2,
        }

        prev = len(prompt) + 2
        for outputs in generate_stream(self.tokenizer, self.model, params, "cuda"):
            yield outputs[prev:].replace("##", "")
            prev = len(outputs)

        print(f"Output generated in {time.time() - t0:.2f}s")


# For local testing, run `modal run -q src.llm_vicuna --input "Where is the best sushi in New York?"`
@stub.local_entrypoint()
def main(input: str):
    model = Vicuna()
    for val in model.generate.call(input):
        print(val, end="", flush=True)
