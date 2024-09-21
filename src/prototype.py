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
        # we use Opus format for audio across the websocket, as it can be safely streamed and decoded in real-time
        self.opus_stream_outbound = sphn.OpusStreamWriter(self.tmp_sample_rate)
        self.opus_stream_inbound = sphn.OpusStreamReader(self.tmp_sample_rate)

    @modal.asgi_app()
    def app(self):
        from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

        web_app = FastAPI()

        @web_app.websocket("/ws")
        async def websocket(ws: WebSocket):
            await ws.accept()
            tasks = []

            # We use asyncio to run multiple loops concurrently, within the context of this single websocket connection
            async def recv_loop():
                '''
                Receives Opus stream across websocket, appends into opus_stream_inboun
                '''
                while True:
                    data = await ws.receive_bytes()

                    if not isinstance(data, bytes):
                        print("received non-bytes message")
                        continue
                    if len(data) == 0:
                        print("received empty message")
                        continue

                    print(f"received {len(data)} bytes")
                    self.opus_stream_inbound.append_bytes(data)

            async def inference_loop():
                '''
                Runs streaming inference on inbound data, and if any response audio is created, appends it to the outbound stream
                '''
                while True:
                    await asyncio.sleep(0.001)
                    pcm = self.opus_stream_inbound.read_pcm()
                    if pcm is None:
                        continue
                    if len(pcm) == 0:
                        continue
                    print("Inferencing on pcm chunk of size", len(pcm))
                    # todo: 
                    # this is where we would run inference
                    # but for now, just echo audio back
                    self.opus_stream_outbound.append_pcm(pcm)


            async def send_loop():
                '''
                Reads outbound data, and sends it across websocket
                '''
                while True:
                    await asyncio.sleep(0.001)
                    msg = self.opus_stream_outbound.read_bytes()
                    if msg is None:
                        continue
                    if len(msg) == 0:
                        continue

                    await ws.send_bytes(msg)
                    print(f"sent {len(msg)} bytes")

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
            except Exception as e:
                print("Exception:", e)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self.opus_stream_inbound.close()
                self.reset_state()

        return web_app