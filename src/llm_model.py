"""
Vicuna 13B language model, 4-bit quantized for faster inference.
Adapted from https://github.com/thisserand/FastChat.git

Path to weights provided for illustration purposes only,
please check the license before using for commercial purposes!
"""
import time

from modal import Image, method, Secret

from vector_store import extract_pii
from .common import get_openai_conversation_model, stub


stub.ai_phone_called_model_image = (
    Image.from_registry(
        "python:3.11-slim",
        setup_dockerfile_commands=[
            "RUN apt-get update",
        ],
    )
    .apt_install("git", "gcc", "build-essential")
    .run_commands(
        "pip install modal langchain openai cohere pymongo pydantic",
    )
)

""

if stub.is_inside(stub.ai_phone_called_model_image):
    t0 = time.time()
    import warnings

    warnings.filterwarnings(
        "ignore", category=UserWarning, message="TypedStorage is deprecated"
    )

    from langchain.prompts import (
        PromptTemplate,
    )

    from langchain.output_parsers import PydanticOutputParser
    from pydantic import BaseModel, Field


@stub.cls(
    image=stub.ai_phone_called_model_image,
    container_idle_timeout=300,
    secret=Secret.from_dotenv(),
)
class AiPhoneModel:
    def __enter__(self):
        t0 = time.time()
        print(f"Model loaded in {time.time() - t0:.2f}s")

    @method()
    async def generate(self, input, history=[]):
        t0 = time.time()
        print(f"The user input is: {input}")
        print(f"The utterance history is: {history}")
        if input == "":
            return

        class InitialOutput(BaseModel):
            personal_information: str = Field(
                description="What is the personal information required?"
            )
            should_press_buttons: bool = Field(description="Do I press buttons?")

        # Set up a parser + inject instructions into the prompt template.
        initial_output_parser = PydanticOutputParser(pydantic_object=InitialOutput)

        template_str = """
        You are a powerful assistant who helps answer questions on my behalf. Your job is to understand what personal information are being requested and whether the response should be pressed in buttons.
        Help me understand the {query}. 

        Could you tell me the personal information being requested? It is possible that there is no personal information being requested, then respond with None. If there are multiple personal information being requested, select the first one.
        If the query requires me to press buttons to respond, return True for should_press_buttons. Otherwise, return False. It is possible that there is no personal information being requested, then respond with None.
        Could you also figure out if the response should be pressed it or not? It is possible that there is no personal information being requested. Then respond with False.

        Some examples:
        Query: This call will be monitored and recorded. And your voice? Welcome to Chase, my name is Benioin. This call will be monitored and recorded, and your voice may be huge for parenting cases. Please enter your debit card, account number, or user ID. Followed by the pound key. To report your debit card lost, stolen or damaged. Or to report unrecognized charges. Press A. For other options, press 2.
        Personal Information: Debit card number
        Should the response be pressed in buttons: True

        Query: Please say your 16 digit card number or social security number. If you don't have your card number, say I don't have it.
        Personal Information: 16 digit card number or social security number
        Should the response be pressed in buttons: False

        Query: Please tell me in a few words why you are calling today.
        Personal Information: None
        Should the response be pressed in buttons: False

        

        {format_instructions}
        """

        prompt = PromptTemplate(
            template=template_str,
            input_variables=["query"],
            partial_variables={
                "format_instructions": initial_output_parser.get_format_instructions()
            },
        )
        _input = prompt.format_prompt(query=input)
        model = get_openai_conversation_model()
        output = model(_input.to_string())
        print(f"THIS IS OUTPUT of llm preparse {output}")
        initial_output_parser.parse(output)

        print(f"Output generated in {time.time() - t0:.2f}s")
        response = (
            "Yes"
            if {initial_output_parser.parse(output).should_press_buttons} == True
            else "No"
        )
        print(
            f"Response for buttons is: {response} {initial_output_parser.parse(output)}"
        )
        if {initial_output_parser.parse(output).personal_information} == "None":
            yield {
                "response": f"Okay I am listening.",
                "should_press_buttons": initial_output_parser.parse(
                    output
                ).should_press_buttons,
                "personal_information": initial_output_parser.parse(
                    output
                ).personal_information,
            }
        else:
            response = f"Let me look for my {initial_output_parser.parse(output).personal_information} and I will be right back."
            yield {
                "response": response,
                "should_press_buttons": initial_output_parser.parse(
                    output
                ).should_press_buttons,
                "personal_information": initial_output_parser.parse(
                    output
                ).personal_information,
            }

        extract_pii(initial_output_parser.parse(output).personal_information)


# For local testing, run `modal run -q src.llm_vicuna --input "Where is the best sushi in New York?"`
@stub.local_entrypoint()
def main(input: str):
    model = AiPhoneModel()
    for val in model.generate.call(input):
        print(val, end="", flush=True)
