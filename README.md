# QuiLLMan: Voice Chat with Moshi

A complete voice chat app powered by a speech-to-speech language model and bidirectional streaming.

On the backend is Kyutai Lab's [Moshi](https://github.com/kyutai-labs/moshi) model, which will continuously listen, plan, and respond to a the user. It uses the [Mimi](https://huggingface.co/kyutai/mimi) streaming encoder/decoder model to maintain an unbroken stream of audio in and out, and a [speech-text foundation model](https://huggingface.co/kyutai/moshiko-pytorch-bf16) to determine when and how to respond.

Thanks to bidirectional websocket streaming and use of the [Opus audio codec](https://opus-codec.org/) for compressing audio across the network, response times on good internet can be nearly instantaneous, closely matching the cadence of human speech.

You can find the demo live [here](https://modal-labs--quillman-web.modal.run/).

![Quillman](https://github.com/user-attachments/assets/afda5874-8509-4f56-9f25-d734b8f1c40a)

This repo is meant to serve as a starting point for your own language model-based apps, as well as a playground for experimentation. Contributions are welcome and encouraged!

[Note: this code is provided for illustration only; please remember to check the license before using any model for commercial purposes.]

## File structure

1. React frontend ([`src/frontend/`](./src/frontend/)), served by [`src/app.py`](./src/app.py)
2. Moshi websocket server ([`src/moshi.py`](./src/moshi.py))

## Developing locally

### Requirements

- `modal` installed in your current Python virtual environment (`pip install modal`)
- A [Modal](http://modal.com/) account (`modal setup`)
- A Modal token set up in your environment (`modal token new`)

### Developing the inference module

The Moshi server is a [Modal class](https://modal.com/docs/reference/modal.Cls#modalcls) module to load the models and maintain streaming state, with a [FastAPI](https://fastapi.tiangolo.com/) http server to expose a websocket interface over the internet.

To run a [development server]((https://modal.com/docs/guide/webhooks#developing-with-modal-serve)) for the Moshi module, run this command from the root of the repo.

```shell
modal serve src.moshi
```

In the terminal output, you'll find a URL for creating a websocket connection.

While the `modal serve` process is running, changes to any of the project files will be automatically applied. `Ctrl+C` will stop the app. 

### Testing the websocket connection
From a seperate terminal, we can test the websocket connection directly from the command line with the `tests/moshi_client.py` client.

It requires non-standard dependencies, which can be installed with:
```shell
python -m venv venv
source venv/bin/activate
pip install -r requirements/requirements-dev.txt
```

With dependencies installed, run the terminal client with:
```shell
python tests/moshi_client.py
```

And begin speaking! Be sure to have your microphone and speakers enabled.

### Developing the http server and frontend

The http server at `src/app.py` is a second [FastAPI](https://fastapi.tiangolo.com/) app, for serving the frontend as static files.

A [development server]((https://modal.com/docs/guide/webhooks#developing-with-modal-serve)) can be run with:

```shell
modal serve src.app
```

Since `src/app.py` imports the `src/moshi.py` module, this also starts the Moshi websocket server.

In the terminal output, you'll find a URL that you can visit to use your app. 
While the `modal serve` process is running, changes to any of the project files will be automatically applied. `Ctrl+C` will stop the app. 

Note that for frontend changes, the browser cache may need to be cleared.

### Deploying to Modal

Once you're happy with your changes, [deploy](https://modal.com/docs/guide/managing-deployments#creating-deployments) your app:

```shell
modal deploy src.app
```

This will deploy both the frontend server and the Moshi websocket server.

Note that leaving the app deployed on Modal doesn't cost you anything! Modal apps are serverless and scale to 0 when not in use.
