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

with image.imports():
    import sphn

@app.cls(
    image=image
)
class Moshi:
    @modal.enter()
    def enter(self):
        self.tmp_sample_rate = 24000
        self.reset_state()

    def reset_state(self):
        self.opus_writer = sphn.OpusStreamWriter(self.tmp_sample_rate)
        self.opus_reader = sphn.OpusStreamReader(self.tmp_sample_rate)

    @modal.asgi_app()
    def app(self):
        from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

        web_app = FastAPI()

        @web_app.websocket("/ws")
        async def websocket(ws: WebSocket):
            await ws.accept()
            tasks = []

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
                    if pcm is None:
                        continue
                    if len(pcm) == 0:
                        continue
                    print("Inferencing on pcm chunk of size", len(pcm))
                    # todo: do inference with pcm
                    self.opus_writer.append_pcm(pcm)


            async def send_loop():
                while True:
                    await asyncio.sleep(0.001)
                    msg = self.opus_writer.read_bytes()
                    if msg is None:
                        continue
                    if len(msg) == 0:
                        continue
                    await ws.send_bytes(msg)
                   

            # This runs all the loops concurrently
            try:
                tasks = [
                    asyncio.create_task(recv_loop()),
                    asyncio.create_task(inference_loop()),
                    asyncio.create_task(send_loop())
                ]
                await asyncio.gather(*tasks)
            
            except WebSocketDisconnect:
                print("WebSocket disconnected")
                self.opus_reader.close()

                # reset the state
                self.opus_writer = sphn.OpusStreamWriter(self.tmp_sample_rate)
                self.opus_reader = sphn.OpusStreamReader(self.tmp_sample_rate)

            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self.opus_reader.close()
                self.reset_state()


        return web_app