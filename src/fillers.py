import modal
import time

from .common import app
from .xtts import XTTS

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
    timeout=120,
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
        self.embeddings = model.encode(filler_sentences, convert_to_tensor=True)
        print(f"Precomputing embeddings took {time.time() - t0:.2f}s")

        # presynthesize filler sentences using XTTS module
        self.xtts = XTTS()
        t0 = time.time()
        count = 0
        for filler in filler_sentences:
            if filler not in cache:
                wav_bytesio = self.xtts.speak.remote(filler)
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
        text_embedding = self.model.encode(text, convert_to_tensor=True)
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
    "Oooh..."
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

    # # General Inquiries
    # "Happy to help.",
    # "I'm all ears.",
    # "Tell me more.",
    # "I'm listening.",
    # "You've got my attention.",
    # "I'm curious to hear more.",
    # "Please continue.",
    # "I'm following you.",
    # "You've piqued my interest.",
    # "I'm intrigued.",

    # # Complex or Technical Questions
    # "This is exciting!",
    # "Let's break it down.",
    # "There's a lot to unpack here.",
    # "Let's start with the basics.",
    # "It's simpler than you might think.",
    # "This is quite intricate.",
    # "We're diving deep here.",
    # "This requires some explanation.",
    # "It's a bit technical, but fascinating.",
    # "This is a nuanced topic.",

    # # Opinion-Based Questions
    # "Here's my take.",
    # "In my opinion,",
    # "Here's my perspective.",
    # "I'd say...",
    # "My thoughts on this are the following.",
    # "If you ask me...",
    # "Here's how I see it.",
    # "To me, it seems that",
    # "My view is that",

    # # Personal or Emotional Topics
    # "I'll try to answer sensitively.",
    # "This seems important to you.",
    # "I'll address this respectfully.",
    # "I understand this might be emotional.",
    # "This is quite personal.",
    # "I appreciate your openness.",
    # "This topic requires delicacy.",
    # "I can see this matters to you.",
    # "Let's approach this gently.",
    # "I'll be mindful in my response.",

    # # Controversial or Sensitive Issues
    # "This is a complex issue.",
    # "There are various perspectives here.",
    # "Let's look at this objectively.",
    # "I'll stick to the facts.",
    # "This topic has many facets.",
    # "It's a nuanced subject.",
    # "There's ongoing debate about this.",
    # "This requires careful consideration.",
    # "It's a multifaceted issue.",
    # "There's no simple answer here.",

    # # Creative or Open-Ended Questions
    # "Let's think outside the box.",
    # "This sparks the imagination.",
    # "The possibilities are endless.",
    # "Let's explore this creatively.",
    # "This calls for innovative thinking.",
    # "We can approach this from many angles.",
    # "This is a chance to be inventive.",
    # "Let's brainstorm on this.",
    # "This opens up many avenues.",
    # "We can get really creative here.",

    # # Clarification or Follow-up
    # "Let me make sure I understand.",
    # "Could you clarify something?",
    # "I want to ensure I've got this right.",
    # "Just to double-check,",
    # "If I'm following correctly,",
    # "To avoid any misunderstanding,",
    # "Let me rephrase that.",
    # "Am I on the right track?",
    # "Is this what you're asking?",
    # "Let's make sure we're aligned."
]
    
@app.local_entrypoint()
def test_filler():
    fillers = Fillers()
    sentences = fillers.neighbors.remote("Help me brainstorm the best approximate nearest neighbor algorithm.", n=2)
    for i, sentence in enumerate(sentences):
        wav_bytesio = fillers.fetch_wav.remote(sentence)
        if wav_bytesio is not None:
            with open(f"/tmp/filler_{i}.wav", "wb") as f:
                f.write(wav_bytesio.getvalue())
            print(f"Output audio for filler sentence `{sentence}` saved to /tmp/filler_{i}.wav")