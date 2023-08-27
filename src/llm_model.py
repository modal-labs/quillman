"""
Vicuna 13B language model, 4-bit quantized for faster inference.
Adapted from https://github.com/thisserand/FastChat.git

Path to weights provided for illustration purposes only,
please check the license before using for commercial purposes!
"""
import time
from pathlib import Path
from modal import Image, method, Secret, Mount

from vector_store import extract_pii
from .common import get_openai_conversation_model, stub

pem_path = Path(__file__).parent.with_name("pem_files").resolve()
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
    mounts=[
        Mount.from_local_dir(pem_path, remote_path="/pem_files")
    
    ]
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
            yield {
                "response": "",
                "should_press_buttons": False,
                "personal_information": None
            }
            return

        class InitialOutput(BaseModel):
            personal_information: str = Field(
                description="What is the personal information required?"
            )
            should_press_buttons: bool = Field(description="Do I press buttons?")

        # Set up a parser + inject instructions into the prompt template.
        initial_output_parser = PydanticOutputParser(pydantic_object=InitialOutput)

        template_str = """
        You are a powerful assistant who is speaking with a customer service representative. The customer service representative might ask you for personal information.
        The customer service representative might ask you to press buttons to take an action.

        If no personal information is being requested, then respond "Personal Information: None"
        Otherwise, respond with "Personal Information: <personal information being requested>"

        If the query requires me to press or dial numbers, return "Should the response be pressed in buttons: True"
        Otherwise, return "Should the response be pressed in buttons: False"
        
        Some examples:
        Query: This call will be monitored and recorded. And your voice? Welcome to Chase, my name is Benioin. This call will be monitored and recorded, and your voice may be huge for parenting cases. Please enter your debit card, account number, or user ID. Followed by the pound key. To report your debit card lost, stolen or damaged. Or to report unrecognized charges. Press A. For other options, press 2.
        Personal Information: Debit card number
        Should the response be pressed in buttons: true

        Query: Please say your 16 digit card number or social security number. If you don't have your card number, say I don't have it.
        Personal Information: 16 digit card number or social security number
        Should the response be pressed in buttons: false

        Query: Please tell me in a few words why you are calling today.
        Personal Information: None
        Should the response be pressed in buttons: false

        Query: To deactivate your Chase account, please dial 2. Welcome back Joe Biden.
        Personal Information: None
        Should the response be pressed in buttons: false

        {format_instructions}

        Help me understand ```{query}```
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
        print(f"the llm_model input: {input}")
        print(f"the llm_model output: {output}")
        initial_output_parser.parse(output)
        
        print(f"Output generated in {time.time() - t0:.2f}s")        
        response = "Yes" if {initial_output_parser.parse(output).should_press_buttons} == True else "No"
        print(f"Response for buttons is: {response} {initial_output_parser.parse(output)}")
        if initial_output_parser.parse(output).personal_information in ("None", "none", "NONE", "no", "No", "NO", None):
            
            class ActionOutput(BaseModel):
                key_to_press: str = Field(
                    description="What key is to be pressed for an action?"
                )

            # Set up a parser + inject instructions into the prompt template.
            action_output_parser = PydanticOutputParser(pydantic_object=ActionOutput)

            action_template_str = """
            You are a powerful assistant who helps answer questions on my behalf. Your job is to understand what buttons can be pressed to take an action with the customer call query.
            Help me understand the {query} and find the number to press.

            Only return the number to press. If there are multiple numbers to press, select the first one.
            If there is no number to press, return "None".

            Some examples:
            Query: Press 2 to cancel your credit card
            key_to_press: 2

            Query: Key in 4 to cancel your hear account balance
            key_to_press: 4

            Query: Dial in 0 to cancel your hear account balance
            key_to_press: 0

            {format_instructions}
            """

            action_prompt = PromptTemplate(
                template=action_template_str,
                input_variables=["query"],
                partial_variables={
                    "format_instructions": action_output_parser.get_format_instructions()
                },
            )
            action_input = action_prompt.format_prompt(query=input)
            action_output = model(action_input.to_string())
            print(f"the llm_model action input: {input}")
            print(f"the llm_model action output: {action_output}")
            action = action_output_parser.parse(action_output) 
            
            if  action.key_to_press in ("None", "none", "NONE", "no", "No", "NO", None):

                yield {
                    "response": "Okay I am listening.",
                    "should_press_buttons": False,
                    "personal_information": initial_output_parser.parse(
                        output
                    ).personal_information,
                }
            else:
                yield {
                    "response": action.key_to_press,
                    "should_press_buttons": True,
                    "personal_information": None
                }

        else:
            response = f"Let me look for my {initial_output_parser.parse(output).personal_information} and I will be right back."
            yield {
                "response": response,
                "should_press_buttons": False,
                "personal_information": initial_output_parser.parse(
                    output
                ).personal_information,
            }
        print(f"Getting the personal information: {initial_output_parser.parse(output).personal_information}")
        pii_response = extract_pii(initial_output_parser.parse(output).personal_information) 
        print(f"THIS IS PII RESPONSE {pii_response}")
        yield {
            'response': pii_response.answer,
            "should_press_buttons": initial_output_parser.parse(
                    output
            ).should_press_buttons,
            "personal_information": pii_response.personal_information,
        }


# For local testing, run `modal run -q src.llm_vicuna --input "Where is the best sushi in New York?"`
@stub.local_entrypoint()
def main(input: str):
    model = AiPhoneModel()
    for val in model.generate.call(input):
        print(val, end="", flush=True)
