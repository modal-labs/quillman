import modal
import asyncio

app = modal.App()

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "sphn",
        "fastapi",
    )
)

@app.cls(

)
class Moshi:
    @modal.enter()
    def enter(self):
        import sphn

        tmp_sample_rate = 24000
        self.opus_writer = sphn.OpusStreamWriter(tmp_sample_rate)
        self.opus_reader = sphn.OpusStreamReader(tmp_sample_rate)

    @modal.asgi_app()
    def app(self):
        from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

        # ERIK TODO FOR TOMORROW
        # this server is untested, use moshi_client.py to stream opus to it. the client is currently broken

        web_app = FastAPI()

        @web_app.websocket("/ws")
        async def websocket(ws: WebSocket):
            await ws.accept()

            # We use asyncio to run multiple loops concurrently, within the context of this single websocket connection

            # Receive Opus data, as chunks of bytes, and append to the opus_reader intake stream
            async def recv_loop():
                while True:
                    data = await ws.receive_bytes()

                    if not isinstance(data, bytes):
                        print("received non-bytes message")
                        continue
                    if len(data) == 0:
                        print("received empty message")
                        continue

                    self.opus_reader.append_bytes(data)


            async def inference_loop():
                while True:
                    await asyncio.sleep(0.001)
                    pcm = self.opus_reader.read_pcm()
                    # todo: do inference with pcm
                    self.opus_writer.append_pcm(pcm)


            async def send_loop():
                while True:
                    await asyncio.sleep(0.001)
                    msg = self.opus_writer.read_bytes()
                    await ws.send_bytes(msg)
                   

            # This runs all the loops concurrently
            try:
                await asyncio.gather(inference_loop(), recv_loop(), send_loop())
            except WebSocketDisconnect:
                print("WebSocket disconnected")

        return web_app