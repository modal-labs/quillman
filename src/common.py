from modal import App, Secret

app = App(name="quillman", secrets=[Secret.from_name("huggingface-key")])
