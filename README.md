# QuiLLMan: Voice Chat with LLMs

A complete chat app that transcribes audio in real-time, streams back a response from a language model, and synthesizes this response as natural-sounding speech.

[This repo](https://github.com/modal-labs/quillman) is meant to serve as a starting point for your own language model-based apps, as well as a playground for experimentation. Contributions are welcome and encouraged!

OpenAI [Whisper V3](https://huggingface.co/openai/whisper-large-v3) is used to produce a transcript, which is then passed into the [LLaMA 3.1 8B Instruct](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct) language model to generate a response, which is then synthesized by Coqui's [XTTS](https://github.com/coqui-ai/TTS) text-to-speech model. All together, this produces a voice-to-voice chat experience.

You can find the demo live [here](https://modal-labs--quillman-web.modal.run/).

[Note: this code is provided for illustration only; please remember to check the license before using any model for commercial purposes.]

## File structure

1. React frontend ([`src/frontend/`](./src/frontend/))
2. FastAPI server ([`src/app.py`](./src/app.py))
3. Whisper transcription module ([`src/whisper.py`](./src/whisper.py))
4. XTTS text-to-speech module ([`src/xtts.py`](./src/xtts.py))
5. LLaMA 3.1 text generation module ([`src/llama.py`](./src/llama.py))

## Developing locally

### Requirements

- `modal` installed in your current Python virtual environment (`pip install modal`)
- A [Modal](http://modal.com/) account (`modal setup`)
- A Modal token set up in your environment (`modal token new`)

### Developing the inference modules

Whisper, XTTS, and Llama each have a [`local_entrypoint`](https://modal.com/docs/reference/modal.App#local_entrypoint)
that is invoked when you execute the module with `modal run`.
This is useful for testing each module standalone, without needing to run the whole app.

For example, to test the Whisper transcription module, run:

```shell
modal run -q src.whisper
```

### Developing the http server and frontend

The HTTP server at `src/app.py` is a [FastAPI](https://fastapi.tiangolo.com/) app that chains the inference modules into a single pipeline.

It also serves the frontend as static files.

To run a [development server](https://modal.com/docs/guide/webhooks#developing-with-modal-serve), execute this command from the root directory of this repo:

```shell
modal serve src.app
```

In the terminal output, you'll find a URL that you can visit to use your app. While the `modal serve` process is running, changes to any of the project files will be automatically applied. `Ctrl+C` will stop the app.

### Deploying to Modal

Once you're happy with your changes, [deploy](https://modal.com/docs/guide/managing-deployments#creating-deployments) your app:

```shell
modal deploy src.app
```

Note that leaving the app deployed on Modal doesn't cost you anything! Modal apps are serverless and scale to 0 when not in use.
