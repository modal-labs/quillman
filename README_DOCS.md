# **QuiLLMan: Voice Chat with LLMs**

[QuiLLMan](https://github.com/modal-labs/quillman) is a complete voice chat application built on Modal: you speak and the chatbot speaks back!

At the core is Kyutai Lab's [Moshi](https://github.com/kyutai-labs/moshi) model, a speech-to-speech language model that will continuously listen, plan, and respond to the user.

Thanks to bidirectional websocket streaming and [Opus audio compression](https://opus-codec.org/), response times from the model across decent internet can closely match the cadence of human speech.

We’ve enjoyed playing around with QuiLLMan enough at Modal HQ that we decided to [share the repo](https://github.com/modal-labs/quillman) and put up [a live demo](https://modal-labs--quillman-web.modal.run/).

Everything — the React frontend and the model backend — is deployed serverlessly, allowing it to automatically scale and ensuring you only pay for the compute you use. Read on to see how Modal makes this easy!

This post provides a high-level walkthrough of the [repo](https://github.com/modal-labs/quillman). We’re looking to add more models and features to this as time goes on, and contributions are welcome!

## **Code overview**

Traditionally, building a bidirectional streaming web application as compute-heavy as QuiLLMan would take a lot of work, and is especially difficult to make it robust and scale to handle many concurrent users.

But with Modal, it’s as simple as writing two different classes and running a CLI command.

Our project structure looks like this:

1. [Moshi websocket server](https://modal.com/docs/examples/llm-voice-chat#language-model): loads an instance of the Moshi model and maintains a bidirectional websocket connection with the client via a [FastAPI Server](https://modal.com/docs/examples/llm-voice-chat#fastapi-server).
2. [React frontend](https://modal.com/docs/examples/llm-voice-chat#react-frontend): runs client-side interaction logic, also served via [FastAPI Server](https://modal.com/docs/examples/llm-voice-chat#fastapi-server).

Let’s go through each of these components in more detail.

You’ll want to have the code handy — look for GitHub links in this guide to see the code for each component.

### **FastAPI Server**

Both frontend and backend are served via a [FastAPI Server](https://fastapi.tiangolo.com/), which is a popular Python web framework for building REST APIs.

On Modal, a function or class method can be exposed as a web endpoint by decorating it with the `@app.asgi_app()` [decorator](https://modal.com/docs/reference/modal.asgi_app#modalasgi_app) and returning an [FastAPI](https://fastapi.tiangolo.com/) app. You're then free to configure the FastAPI server however you like, including adding middleware, serving static files, and running websockets.

### **Language Model**

The backend is built on Kyutai Lab's [Moshi](https://github.com/kyutai-labs/moshi), a speech-to-speech language model built for streaming.

Traditionally, a speech-to-speech chat app requires three distinct modules: speech-to-text, text-to-text, and text-to-speech. Passing data between these modules quickly introduces bottlenecks, and can limit the speed of the app. Moshi bundling all modalities in one model decreases latency, and makes for a much simpler app.

Under the hood, Moshi uses the [Mimi](https://huggingface.co/kyutai/mimi) streaming encoder/decoder model to maintain an unbroken stream of audio in and out. The encoded audio is processed by a [speech-text foundation model](https://huggingface.co/kyutai/moshiko-pytorch-bf16), which uses an internal monologue to determine when and how to respond.

This streaming model introduces a few challenges not normally seen in inference backends:
1. The model is *stateful*, meaning it maintains context for the conversation so far. This requires a unique model instance for each user conversation, a GPU per user session, which is normally not an easy feat.
2. The model is *streaming*, so it's not as simple as a POST request. We must find a way to stream audio data in and out, and do it faster than human speech so playback is seamless.

We solve both of these in `src/moshi.py`, using a few Modal features:

**For the stateful model**, we maintain a 1:1 mapping of users to GPUs simply by limiting concurrent connections to one, with the `allow_concurrent_inputs` parameter.

```python
@app.cls(
    image=image,
    gpu="A10G",
    ...,
    allow_concurrent_inputs=1, # ensure only one user at a time
)
class Moshi:
    # ...
```

With this setting, if a new user connects, a new GPU instance is created!  When any user disconnects, the state of their model is reset and that GPU instance is returned to the warm pool for re-use. Be aware that a GPU per user is not going to be cheap, but it's the simplest way to ensure user sessions are isolated and GPU resources are not contested.

**For streaming**, we use FastAPI's support for bidirectional websockets, which allows clients to establish a single connection at the start of their session, and stream audio data both ways.

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

To run a [development server]((https://modal.com/docs/guide/webhooks#developing-with-modal-serve)) for the Moshi module, run this command from the root of the repo.

```shell
modal serve src.moshi
```

In the terminal output, you'll find a URL for creating a websocket connection.

### **React Frontend**

The frontend is a static React app, served rom `src/app.py` and can be found in the  `src/frontend` directory.

We use the [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API) to record audio from the user's microphone and playback audio responses from the model. 

For efficient audio transmission, we use the [Opus codec](https://opus-codec.org/) to compress audio across the network. Opus recording and playback are supported by the [opus-recorder](https://github.com/chris-rudmin/opus-recorder) and [ogg-opus-decoder](https://github.com/eshaz/wasm-audio-decoders/tree/master/src/ogg-opus-decoder) libraries.

To serve the frontend assets, run this command from the root of the repo.
```shell
modal serve src.app
```

This also spins up an endpoint for the Moshi websocket server.

## **Steal this example**

The code for this entire example is [available on GitHub](https://github.com/modal-labs/quillman). Follow the instructions in the README for how to run or deploy it yourself on Modal.