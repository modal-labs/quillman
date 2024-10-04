# QuiLLMan: Voice Chat with Moshi

[QuiLLMan](https://github.com/modal-labs/quillman) is a complete voice chat application built on Modal: you speak and the chatbot speaks back!

At the core is Kyutai Lab's [Moshi](https://github.com/kyutai-labs/moshi) model, a speech-to-speech language model that will continuously listen, plan, and respond to the user.

Thanks to bidirectional websocket streaming and [Opus audio compression](https://opus-codec.org/), response times on good internet can be nearly instantaneous, closely matching the cadence of human speech.

You can find the demo live [here](https://modal-labs--quillman-web.modal.run/).

![Quillman](https://github.com/user-attachments/assets/afda5874-8509-4f56-9f25-d734b8f1c40a)

Everything — from the React frontend to the model backend — is deployed serverlessly on Modal, allowing it to automatically scale and ensuring you only pay for the compute you use.

This page provides a high-level walkthrough of the [GitHub repo](https://github.com/modal-labs/quillman).

## Code overview

Traditionally, building a bidirectional streaming web application as compute-heavy as QuiLLMan would take a lot of work, and it's especially difficult to make it robust and scale to handle many concurrent users.

But with Modal, it’s as simple as writing two different classes and running a CLI command.

Our project structure looks like this:

1. [Moshi Websocket Server](https://modal.com/docs/examples/llm-voice-chat#moshi-websocket-server): loads an instance of the Moshi model and maintains a bidirectional websocket connection with the client.
2. [React Frontend](https://modal.com/docs/examples/llm-voice-chat#react-frontend): runs client-side interaction logic.

Let’s go through each of these components in more detail.

### FastAPI Server

Both frontend and backend are served via a [FastAPI Server](https://fastapi.tiangolo.com/), which is a popular Python web framework for building REST APIs.

On Modal, a function or class method can be exposed as a web endpoint by decorating it with [`@app.asgi_app()`](https://modal.com/docs/reference/modal.asgi_app#modalasgi_app) and returning a FastAPI app. You're then free to configure the FastAPI server however you like, including adding middleware, serving static files, and running websockets.

### Moshi Websocket Server

Traditionally, a speech-to-speech chat app requires three distinct modules: speech-to-text, text-to-text, and text-to-speech. Passing data between these modules introduces bottlenecks, and can limit the speed of the app and forces a turn-by-turn conversation which can feel unnatural.

Kyutai Lab's [Moshi](https://github.com/kyutai-labs/moshi) bundles all modalities into one model, which decreases latency and makes for a much simpler app.

Under the hood, Moshi uses the [Mimi](https://huggingface.co/kyutai/mimi) streaming encoder/decoder model to maintain an unbroken stream of audio in and out. The encoded audio is processed by a [speech-text foundation model](https://huggingface.co/kyutai/moshiko-pytorch-bf16), which uses an internal monologue to determine when and how to respond.

Using a streaming model introduces a few challenges not normally seen in inference backends:

1. The model is _stateful_, meaning it maintains context of the conversation so far. This means a model instance cannot be shared between user conversations, so we must run a unique GPU per user session, which is normally not an easy feat!
2. The model is _streaming_, so the interface around it is not as simple as a POST request. We must find a way to stream audio data in and out, and do it fast enough for seamless playback.

We solve both of these in `src/moshi.py`, using a few Modal features.

To solve statefulness, we just spin up a new GPU per concurrent user.
That's easy with Modal!

```python
@app.cls(
    image=image,
    gpu="A10G",
    container_idle_timeout=300,
    ...
)
class Moshi:
    # ...
```

With this setting, if a new user connects, a new GPU instance is created! When any user disconnects, the state of their model is reset and that GPU instance is returned to the warm pool for re-use (for up to 300 seconds). Be aware that a GPU per user is not going to be cheap, but it's the simplest way to ensure user sessions are isolated.

For streaming, we use FastAPI's support for bidirectional websockets. This allows clients to establish a single connection at the start of their session, and stream audio data both ways.

Just as a FastAPI server can run from a Modal function, it can also be attached to a Modal class method, allowing us to couple a prewarmed Moshi model to a websocket session.

```python
    @modal.asgi_app()
    def web(self):
        from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect

        web_app = FastAPI()
        @web_app.websocket("/ws")
        async def websocket(ws: WebSocket):
            with torch.no_grad():
                await ws.accept()

                # handle user session

                # spawn loops for async IO
                async def recv_loop():
                    while True:
                        data = await ws.receive_bytes()
                        # send data into inference stream...

                async def send_loop():
                    while True:
                        await asyncio.sleep(0.001)
                        msg = self.opus_stream_outbound.read_bytes()
                        # send inference output to user ...
```

To run a [development server](https://modal.com/docs/guide/webhooks#developing-with-modal-serve) for the Moshi module, run this command from the root of the repo.

```shell
modal serve src.moshi
```

In the terminal output, you'll find a URL for creating a websocket connection.

### React Frontend

The frontend is a static React app, found in the `src/frontend` directory and served by `src/app.py`.

We use the [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API) to record audio from the user's microphone and playback audio responses from the model.

For efficient audio transmission, we use the [Opus codec](https://opus-codec.org/) to compress audio across the network. Opus recording and playback are supported by the [`opus-recorder`](https://github.com/chris-rudmin/opus-recorder) and [`ogg-opus-decoder`](https://github.com/eshaz/wasm-audio-decoders/tree/master/src/ogg-opus-decoder) libraries.

To serve the frontend assets, run this command from the root of the repo.

```shell
modal serve src.app
```

Since `src/app.py` imports the `src/moshi.py` module, this `serve` command also serves the Moshi websocket server as its own endpoint.

## Deploy

When you're ready to go live, use the `deploy` command to deploy the app to Modal.

```shell
modal deploy src.app
```

## Steal this example

The code for this entire example is [available on GitHub](https://github.com/modal-labs/quillman), so feel free to fork it and make it your own!
