"""
Moshi websocket web service.
"""

import modal
import asyncio
import time

from .common import app

model_path = "/models"
model_volume_cache = modal.Volume.from_name("moshi-model-cache", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "moshi==0.1.0",
        "fastapi==0.115.5",
        "huggingface_hub==0.24.7",
        "hf_transfer==0.1.8",
        "sphn==0.1.4",
    )
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "HF_HUB_CACHE": model_path,
        }
    )
)

with image.imports():
    from huggingface_hub import hf_hub_download
    import torch
    from moshi.models import loaders, LMGen
    import sentencepiece
    import sphn
    import numpy as np


@app.cls(
    image=image,
    gpu="A10G",
    scaledown_window=300,
    timeout=600,
    volumes={model_path: model_volume_cache},
)
class Moshi:
    @modal.enter()
    def download_model(self):
        hf_hub_download(loaders.DEFAULT_REPO, loaders.MOSHI_NAME)
        hf_hub_download(loaders.DEFAULT_REPO, loaders.MIMI_NAME)
        hf_hub_download(loaders.DEFAULT_REPO, loaders.TEXT_TOKENIZER_NAME)

    @modal.enter()
    def enter(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        mimi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MIMI_NAME)
        self.mimi = loaders.get_mimi(mimi_weight, device=self.device)
        self.mimi.set_num_codebooks(8)
        self.frame_size = int(self.mimi.sample_rate / self.mimi.frame_rate)

        moshi_weight = hf_hub_download(loaders.DEFAULT_REPO, loaders.MOSHI_NAME)
        self.moshi = loaders.get_moshi_lm(moshi_weight, device=self.device)
        self.lm_gen = LMGen(
            self.moshi,
            # Sampling params
            temp=0.8,
            temp_text=0.8,
            top_k=250,
            top_k_text=25,
        )

        self.mimi.streaming_forever(1)
        self.lm_gen.streaming_forever(1)

        tokenizer_config = hf_hub_download(
            loaders.DEFAULT_REPO, loaders.TEXT_TOKENIZER_NAME
        )
        self.text_tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_config)

        # Warmup them GPUs
        for chunk in range(4):
            chunk = torch.zeros(
                1, 1, self.frame_size, dtype=torch.float32, device=self.device
            )
            codes = self.mimi.encode(chunk)
            for c in range(codes.shape[-1]):
                tokens = self.lm_gen.step(codes[:, :, c : c + 1])
                if tokens is None:
                    continue
                _ = self.mimi.decode(tokens[:, 1:])
        torch.cuda.synchronize()

    def reset_state(self):
        # we use Opus format for audio across the websocket, as it can be safely streamed and decoded in real-time
        self.opus_stream_outbound = sphn.OpusStreamWriter(self.mimi.sample_rate)
        self.opus_stream_inbound = sphn.OpusStreamReader(self.mimi.sample_rate)

        # LLM is stateful, maintaining chat history, so reset it on each connection
        self.mimi.reset_streaming()
        self.lm_gen.reset_streaming()

    @modal.asgi_app()
    def web(self):
        from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

        web_app = FastAPI()

        @web_app.get("/status")
        async def status():
            return Response(status_code=200)

        @web_app.websocket("/ws")
        async def websocket(ws: WebSocket):
            with torch.no_grad():
                await ws.accept()

                # Clear model chat history and any buffered audio
                self.reset_state()

                print("Session started")
                tasks = []

                # We use asyncio to run multiple loops concurrently, within the context of this single websocket connection
                async def recv_loop():
                    """
                    Receives Opus stream across websocket, appends into opus_stream_inboun
                    """
                    while True:
                        data = await ws.receive_bytes()

                        if not isinstance(data, bytes):
                            print("received non-bytes message")
                            continue
                        if len(data) == 0:
                            print("received empty message")
                            continue
                        self.opus_stream_inbound.append_bytes(data)

                async def inference_loop():
                    """
                    Runs streaming inference on inbound data, and if any response audio is created, appends it to the outbound stream
                    """
                    all_pcm_data = None
                    while True:
                        await asyncio.sleep(0.001)
                        pcm = self.opus_stream_inbound.read_pcm()
                        if pcm is None:
                            continue
                        if len(pcm) == 0:
                            continue

                        if pcm.shape[-1] == 0:
                            continue
                        if all_pcm_data is None:
                            all_pcm_data = pcm
                        else:
                            all_pcm_data = np.concatenate((all_pcm_data, pcm))

                        # infer on each frame
                        while all_pcm_data.shape[-1] >= self.frame_size:
                            t0 = time.time()

                            chunk = all_pcm_data[: self.frame_size]
                            all_pcm_data = all_pcm_data[self.frame_size :]

                            chunk = torch.from_numpy(chunk)
                            chunk = chunk.to(device=self.device)[None, None]

                            # inference on audio chunk
                            codes = self.mimi.encode(chunk)

                            # language model inference against encoded audio
                            for c in range(codes.shape[-1]):
                                tokens = self.lm_gen.step(codes[:, :, c : c + 1])

                                if tokens is None:
                                    # model is silent
                                    continue

                                assert tokens.shape[1] == self.lm_gen.lm_model.dep_q + 1
                                main_pcm = self.mimi.decode(tokens[:, 1:])
                                main_pcm = main_pcm.cpu()
                                self.opus_stream_outbound.append_pcm(
                                    main_pcm[0, 0].numpy()
                                )

                                text_token = tokens[0, 0, 0].item()
                                if text_token not in (0, 3):
                                    text = self.text_tokenizer.id_to_piece(text_token)
                                    text = text.replace("▁", " ")
                                    msg = b"\x02" + bytes(
                                        text, encoding="utf8"
                                    )  # prepend "\x02" as a tag to indicate text
                                    await ws.send_bytes(msg)

                async def send_loop():
                    """
                    Reads outbound data, and sends it across websocket
                    """
                    while True:
                        await asyncio.sleep(0.001)
                        msg = self.opus_stream_outbound.read_bytes()
                        if msg is None:
                            continue
                        if len(msg) == 0:
                            continue
                        msg = b"\x01" + msg  # prepend "\x01" as a tag to indicate audio
                        await ws.send_bytes(msg)

                # This runs all the loops concurrently
                try:
                    tasks = [
                        asyncio.create_task(recv_loop()),
                        asyncio.create_task(inference_loop()),
                        asyncio.create_task(send_loop()),
                    ]
                    await asyncio.gather(*tasks)

                except WebSocketDisconnect:
                    print("WebSocket disconnected")
                    await ws.close(code=1000)
                except Exception as e:
                    print("Exception:", e)
                    await ws.close(code=1011)  # Internal error
                    raise e
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    # self.opus_stream_inbound.close()
                    self.reset_state()

        return web_app
