from modal import Stub

stub = Stub(name="quillman")


def get_openai_conversation_model():
    from langchain.llms import OpenAI

    model_name = "gpt-4-0613"
    temperature = 0.0
    return OpenAI(model_name=model_name, temperature=temperature)
