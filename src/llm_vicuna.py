"""
Vicuna 13B language model, 4-bit quantized for faster inference.
Adapted from https://github.com/thisserand/FastChat.git

Path to weights provided for illustration purposes only,
please check the license before using for commercial purposes!
"""
import time
from pathlib import Path

from modal import Image, method, Secret
from .common import stub




stub.ai_phone_called_model_image = (
    Image.from_registry(
        "python:3.11-slim",
        setup_dockerfile_commands=[
            "RUN apt-get update",
        ],
    )
    .apt_install("git", "gcc", "build-essential")
    .run_commands(
        "pip install modal langchain openai pydantic",
    )
)

""

if stub.is_inside(stub.ai_phone_called_model_image):
    t0 = time.time()
    import warnings

    warnings.filterwarnings(
        "ignore", category=UserWarning, message="TypedStorage is deprecated"
    )

    from langchain.prompts import PromptTemplate, ChatPromptTemplate, HumanMessagePromptTemplate
    from langchain.llms import OpenAI
    from langchain.chat_models import ChatOpenAI

    from langchain.output_parsers import PydanticOutputParser
    from pydantic import BaseModel, Field, validator
    from typing import List


@stub.cls(image=stub.ai_phone_called_model_image, container_idle_timeout=300, secret=Secret.from_dotenv())
class AiPhoneModel:
    def __enter__(self):
        t0 = time.time()
        print(f"Model loaded in {time.time() - t0:.2f}s")

    @method()
    async def generate(self, input, history=[]):
        t0 = time.time()
        print(f"The VICUNA generate input is: {input}")
        print(f"The VICUNA generate history is: {history}")
        if input == "":
            return
        model_name = 'gpt-4-0613'
        temperature = 0.0
        model = OpenAI(model_name=model_name, temperature=temperature)

        class InitialOutput(BaseModel):
            personal_information: str = Field(description="What is the personal information required?")
            should_press_buttons: bool = Field(description="Should the response be pressed in buttons?")

        # Set up a parser + inject instructions into the prompt template.
        initial_output_parser = PydanticOutputParser(pydantic_object=InitialOutput)

        template_str = """
        You are a powerful assistant who helps answer questions on my behalf. Your job is to understand what personal information are being requested and whether the response should be pressed in buttons.
        Help me understand the {query}. 
        Could you tell me the personal information being requested? It is possible that there is no personal information being requested. Then respond with None.
        Could you also figure out if the response should be pressed it or not? It is possible that there is no personal information being requested. Then respond with False.

        {format_instructions}
        """
        prompt = PromptTemplate(
            template=template_str,
            input_variables=["query"],
            partial_variables={"format_instructions": initial_output_parser.get_format_instructions()}
        )
        _input = prompt.format_prompt(query=input)
        output = model(_input.to_string())
        initial_output_parser.parse(output)
        
        print(f"Output generated in {time.time() - t0:.2f}s")        
        response = "Yes" if {initial_output_parser.parse(output).should_press_buttons} else "No"
        return f"The personal information being requested is {initial_output_parser.parse(output).personal_information} and the response should be pressed in buttons: {response}"

        


# For local testing, run `modal run -q src.llm_vicuna --input "Where is the best sushi in New York?"`
@stub.local_entrypoint()
def main(input: str):
    model = AiPhoneModel()
    for val in model.generate.call(input):
        print(val, end="", flush=True)
