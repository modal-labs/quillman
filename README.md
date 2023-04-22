# QuiLLMan: Voice Chat with LLMs

A complete chat app that transcribes audio in real-time, streams back a response from a language model, and synthesizes this response as natural-sounding speech.

This repo is meant to serve as a starting point for your own language model-based apps, as well as a playground for experimentation. Contributions are welcome and encouraged!

![quillman](https://user-images.githubusercontent.com/5786378/233804923-c13627de-97db-4050-a36b-62d955db9c19.gif)

The language model used is [Vicuna](https://github.com/lm-sys/FastChat), and we're planning on adding support for more models soon (requests and contributions welcome). [OpenAI Whisper](https://github.com/openai/whisper) is used for transcription, and [Metavoice Tortoise TTS](https://github.com/metavoicexyz/tortoise-tts) is used for text-to-speech. The entire app, including the frontend, is made to be deployed serverlessly on [Modal](http://modal.com/).

You can find the demo live [here](https://modal-labs--quillman-web.modal.run/).

[Note: this code is provided for illustration only; please remember to check the license before using any model for commercial purposes.]

## File structure

1. React frontend ([`src/frontend/`](./src/frontend/))
2. FastAPI server ([`src/api.py`](./src/api.py))
3. Whisper transcription module ([`src/transcriber.py`](./src/transcriber.py))
4. Tortoise text-to-speech module ([`src/tts.py`](./src/tts.py))
5. Vicuna language model module ([`src/llm_vicuna.py`](./src/llm_vicuna.py))

Read the accompanying [docs](https://modal.com/docs/guide/llm-voice-chat) for a detailed look at each of these components.

## Developing locally

### Requirements

- `modal-client` installed in your current Python virtual environment (`pip install modal-client`)
- A [Modal](http://modal.com/) account
- A Modal token set up in your environment (`modal token new`)

### Develop on Modal

To [serve](https://modal.com/docs/guide/webhooks#developing-with-modal-serve) the app on Modal, run this command from the root directory of this repo:

```shell
modal serve src.app
```

In the terminal output, you'll find a URL that you can visit to use your app. While the `modal serve` process is running, changes to any of the project files will be automatically applied. `Ctrl+C` will stop the app.

### Deploy to Modal

Once you're happy with your changes, [deploy](https://modal.com/docs/guide/managing-deployments#creating-deployments) your app:

```shell
modal deploy src.app
```

[Note that leaving the app deployed on Modal doesn't cost you anything! Modal apps are serverless and scale to 0 when not in use.]
