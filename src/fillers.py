from re import TEMPLATE
import modal
import time

from .common import app
from .xtts import XTTS

FILLER_PROMPT_TEMPLATE = '''
In a conversation between a human and an AI assistant, the AI is empethetic.
To fill time while thinking, it says a contextually relevant filler response:
"{filler}" 
'''

TRANSCRIPT_PROMPT_TEMPLATE = '''
In a conversation between a human and an AI assistant, the AI is empethetic.
The user says:
"{user_input}"
Meanwhile, the AI assistant is thinking about a contextually relevant response.
'''


cache = modal.Dict.from_name("filler-cache", create_if_missing=True)

filler_img = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "sentence-transformers",
        "torch"
    )
)

with filler_img.imports():
    from sentence_transformers import SentenceTransformer
    import torch

@app.cls(
    image=filler_img,
    gpu="T4", # can be cheap
    container_idle_timeout=120,
    timeout=300,
)
class Fillers:
    def __init__(self):
        pass

    @modal.build()
    def download_model(self):
        SentenceTransformer("all-MiniLM-L6-v2")

    @modal.enter()
    def enter(self):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = SentenceTransformer("all-MiniLM-L6-v2").to(device)
        self.model = model

        # precompute and cache embeddings
        t0 = time.time()
        formatted = [FILLER_PROMPT_TEMPLATE.format(filler=filler) for filler in filler_sentences]
        self.embeddings = self.model.encode(formatted, convert_to_tensor=True)
        print(f"Precomputing embeddings took {time.time() - t0:.2f}s")


    @modal.method()
    def prefill(self):
        # presynthesize filler sentences using XTTS module
        self.xtts = XTTS()
        t0 = time.time()
        count = 0
        for filler in filler_sentences:
            if filler not in cache:
                _, wav_bytesio = self.xtts.speak.remote(filler)
                cache[filler] = wav_bytesio
                count += 1
                print("Synthesized and cached filler:", filler)
        print(f"Synthesizing and caching {count} fillers took {time.time() - t0:.2f}s")

    @modal.method()
    def prewarm(self):
        # no-op to prewarm model instance
        pass

    @modal.method()
    def neighbors(self, text, n=1):
        '''
        Use cosine similarity to find the top n most similar sentences
        '''

        # Since we have a relatively small number of fillers, we can just do a brute-force cosine similarity search
        # But for larger sets of fillers, we'd use ANNOY, an excellent library for finding approximate nearest neighbors (oh yeah)
        text_embedding = self.model.encode(TRANSCRIPT_PROMPT_TEMPLATE.format(user_input=text), convert_to_tensor=True)
        similarities = torch.nn.functional.cosine_similarity(text_embedding, self.embeddings)
        top_n_similarities, top_n_indices = torch.topk(similarities, n)

        return [filler_sentences[i] for i in top_n_indices]
    
    @modal.method()
    def fetch_wav(self, sentence):
        if sentence in cache:
            return cache[sentence]
        else:
            print("Not in cache:", sentence)
            return None
    
        
filler_sentences = [
    # Vocalizations
    "Ooof!",
    "Aaah!",
    "Wow!",
    "Tada!",
    "Ohhh!",
    "Oooh...",
    "Hmmm...",
    "Eeee!",
    "Huh?",
    "Whoa!",
    "Yikes!",
    "Sheesh!",
    "Phew!",
    "Aha!",
    "Oh my!",
    "Gosh!",
    "Ahem!",
    "Bam!",
    "Oops!",
    "Aww!",

    # Quick Talk
    "Pardon me?",
    "Hey!",
    "I see.",
    "Totally!",
    "Sure.",
    "Okay.",
    "Alright.",
    "Yes!",
    "That's right.",
    "I agree.",
    "I'm with you.",
    "I think so.",
    "Got it.",
    "Fair enough.",
    "Makes sense.",
    "Interesting.",
    "No way!",
    "You don't say!",
    "Go on.",
    "Really?",
    "Is that so?",
    "Tell me more.",
    "Say what?",
    "Come again?",
    "How about that?",
    "Well, well, well.",
    "Oh, I see.",
    "Indeed!",
    "Naturally.",
    "Of course!",
    "Absolutely!",
    "Good point.",
    "Well said.",
    "True that.",
    "Right on!",
    "For real?",
    "You bet!",
    "No kidding!",
    "As if!",
    "Get out!",
    "Seriously?",
    "That's crazy!",
    "Who knew?",
    "Fancy that!",
    "How so?",
    "Do tell.",
    "Oh really?",
    "Is it?",
    "Why so?",
    "What gives?",

    # Responses to direct questions
    "Let me think...",
    "Good question.",
    "That's tricky.",
    "Well now...",
    "Hmm, let's see.",
    "Give me a sec.",
    "I'm not sure.",
    "It depends.",
    "Possibly?",
    "Maybe so.",
    "Could be.",
    "Hard to say.",
    "That's debatable.",
    "In what way?",
    "Interesting question.",
    "I wonder...",
    "That's complex.",
    "Not necessarily.",
    "Yes and no.",
    "To some extent.",
    "In a sense.",
    "More or less.",
    "Up to a point.",
    "That's subjective.",
    "It varies.",
    "Case by case.",
]
    
@app.local_entrypoint()
def test_filler():
    fillers = Fillers()
    sentences = fillers.neighbors.remote("What's the best approximate nearest neighbor algorithm?", n=1)
    for i, sentence in enumerate(sentences):
        wav_bytesio = fillers.fetch_wav.remote(sentence)
        if wav_bytesio is not None:
            with open(f"/tmp/filler_{i}.wav", "wb") as f:
                f.write(wav_bytesio.getvalue())
            print(f"Output audio for filler sentence `{sentence}` saved to /tmp/filler_{i}.wav")