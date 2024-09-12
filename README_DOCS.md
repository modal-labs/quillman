# **QuiLLMan: Voice Chat with LLMs**

[QuiLLMan](https://github.com/modal-labs/quillman) is a complete voice chat application built on Modal: you speak and the chatbot speaks back!

OpenAI's [Whisper V3](https://huggingface.co/openai/whisper-large-v3) is used to produce a transcript, which is then passed into the [Zepyhr](https://arxiv.org/abs/2310.16944) language model to generate a response, which is then synthesized by Coqui's [XTTS](https://github.com/coqui-ai/TTS) text-to-speech model. All together, this produces a voice-to-voice chat experience.

We’ve enjoyed playing around with QuiLLMan enough at Modal HQ that we decided to [share the repo](https://github.com/modal-labs/quillman) and put up [a live demo](https://modal-labs--quillman-web.modal.run/).

Everything — the React frontend, the backend API, the LLMs — is deployed serverlessly, allowing it to automatically scale and ensuring you only pay for the compute you use. Read on to see how Modal makes this easy!

[TODO: GIF HERE]

This post provides a high-level walkthrough of the [repo](https://github.com/modal-labs/quillman). We’re looking to add more models and features to this as time goes on, and contributions are welcome!

## **Code overview**

Traditionally, building a robust serverless web application as complex as QuiLLMan would require a lot of work — you’re setting up a backend API and three different inference modules, running in separate custom containers and autoscaling independently.

But with Modal, it’s as simple as writing 4 different classes and running a CLI command.

Our project structure looks like this:

1. [Language model module](https://modal.com/docs/examples/llm-voice-chat#language-model): continues a text conversation with a text reply.
2. [Transcription module](https://modal.com/docs/examples/llm-voice-chat#transcription): converts speech audio into text.
3. [Text-to-speech module](https://modal.com/docs/examples/llm-voice-chat#text-to-speech): converts text into speech.
4. [FastAPI server](https://modal.com/docs/examples/llm-voice-chat#fastapi-server): runs server-side app logic.
5. [React frontend](https://modal.com/docs/examples/llm-voice-chat#react-frontend): runs client-side interaction logic.

Let’s go through each of these components in more detail.

You’ll want to have the code handy — look for GitHub links in this guide to see the code for each component.

### **Language model**

Language models are trained to predict what text will come at the end of incomplete text. From this simple task emerge the sparks of artificial general intelligence.

In this case, we want to predict the text that a helpful, friendly assistant might write to continue a conversation with a user.

As with all Modal applications, we start by describing the environment (the container `Image`), which we construct via Python method chaining:

`llama_image = (    modal.Image.debian_slim(python_version="3.10")    .pip_install(        "transformers==4.44.2",        "vllm==0.6.0",        "torch==2.4.0",        "hf_transfer==0.1.8",        "huggingface_hub==0.24.6",    )    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"}))`

Copy

The chain starts with a base Debian container installs `python_version` 3.10, then uses [`pip` to `install` our Python packages we need](https://modal.com/docs/reference/modal.Image#pip_install). Pinning versions of our dependencies ensures that the built image is reproducible.

We use [VLLM](https://github.com/vllm-project/vllm), a high-performance open-source library for running large language models on CPUs and GPUs, to run the Llama model. This server scales to handle multiple concurrent requests, keeping costs down for our LLM module.

The models we use define a [`generate`](TODO: permalink to spot in code) function that constructs an input to our language model from a prompt template, the conversation history, and the latest text from the user. Then, it `yield`s (streams) words as they are produced. Remote Python generators work out-of-the-box in Modal, so building streaming interactions is easy.

Although we’re going to call this model from our backend API, it’s useful to test it directly as well. To do this, we define a [`local_entrypoint`](https://modal.com/docs/guide/apps#entrypoints-for-ephemeral-apps):

`@app.local_entrypoint()def main(prompt: str):    model = Llama()    for val in model.generate.remote_gen(prompt):        print(val, end="", flush=True)`

Copy

Now, we can [`run`](https://modal.com/docs/guide/apps#ephemeral-apps) the model with a prompt of our choice from the terminal:

`modal run -q src.llama --prompt "How do antihistamines work?"`

TODO: GIF HERE

### **Transcription**

In the Whisper module, we define a Modal class that uses [OpenAI’s Whisper V3](https://huggingface.co/openai/whisper-large-v3) to transcribe audio in real-time.

To speed up transcription, we use [Flash-Attention](https://github.com/Dao-AILab/flash-attention), which requires some additional container customization such as using a CUDA-devel image to get access to `nvcc`. Optionally, [check out this guide](https://modal.com/docs/guide/cuda) if you'd like to optionally understand how CUDA works on Modal.

We’re using an [A10G GPU](https://www.nvidia.com/en-us/data-center/products/a10-gpu/) for transcriptions, which lets us transcribe most segments in under 2 seconds. 



### **Text-to-speech**

The text-to-speech module uses the Coqui [XTTS](https://github.com/coqui-ai/TTS) text-to-speech model, offering a variety of voices and languages. We're able to parallelize the TTS generation by splitting transcripts into smaller chunks across multiple GPUs

### **FastAPI server**

The file `app.py` is a [FastAPI](https://fastapi.tiangolo.com/) app that chains the inference modules into a single pipeline. We can serve this app over the internet without any extra effort on top of writing the `localhost` version by slapping on an [`@asgi_app`](https://modal.com/docs/guide/webhooks#serving-asgi-and-wsgi-apps) decorator.

To make the experience as conversational as possible, it's important to focus on reducing the latency between the end of the user's speech and the start of the reply audio playback.

Because we're using GPUs, we have an advantage: it's faster than real-time.

Transcription happens faster than the user's real-time speech. So while the user is speaking, we can stream that audio to the server in chunks, and have the transcript mostly complete by the time the user finishes speaking.

And text generation and text-to-speech happens faster than the audio playback. So if we generate, synthesize, and return the first sentence of the response ASAP, we can get it playing in the browser while we finish the rest of the response in the background.

This makes the user's perception of latency as short as possible, with us hiding the majority of the latency during the spoken interactions.

We use these techniques in `/pipeline` to achieve this:
1. The `/pipeline` endpoint is a websocket connection, enabling streaming audio in chunks.
2. All intermediate data in the pipeline is streamed through python generators between inference modules. 
3. We start transcribing even before the user finishes speaking.
4. The transcription is done in parallel using Modal [spawn](https://modal.com/docs/reference/modal.Function#spawn), since each chunk is independent of the others. We use spawn rather than map since we're in an async block while receiving audio from the websocket.
5. The text response generation is a Modal [remote generator function](https://modal.com/docs/reference/modal.Function#remote_gen), streaming output as it's generated. This can be fed directly into the text-to-speech module, even before the full transcript is available.
6. The text-to-speech is done in parallel using Modal [map](https://modal.com/docs/reference/modal.Function#map), since each sentence is independent of the others.
7. We stream synthesized audio back to the client as it's generated, so the browser can start playback as soon as possible.

In addition, we add a `/prewarm` endpoint, to be called by the client before they run the first `/pipeline` request. This ensures all on-GPU models are loaded and ready to go.


### **React frontend**

We use the [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API) to record snippets of audio from the user’s microphone. The file [`src/frontend/processor.js`](https://github.com/modal-labs/quillman/blob/main/src/frontend/processor.js) defines an [AudioWorkletProcessor](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorkletProcessor) that distinguishes between speech and silence, and emits events for speech buffers so we can transcribe them.

The frontend maintains a state machine to manage the state of the conversation. This is implemented with the help of the incredible [XState](https://github.com/statelyai/xstate) library.

## **Steal this example**

The code for this entire example is [available on GitHub](https://github.com/modal-labs/quillman). Follow the instructions in the README for how to run or deploy it yourself on Modal.