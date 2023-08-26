from langchain.schema.document import Document
from typing import List
import os

from common import get_openai_conversation_model


def get_mongo_client():
    from pymongo import MongoClient
    from pymongo.server_api import ServerApi

    return MongoClient(
        os.getenv("MONGODB_ATLAS_CLUSTER_URI"),
        tls=True,
        tlsCertificateKeyFile=os.getenv("MONGODB_PEM_LOCATION"),
        server_api=ServerApi("1"),
    )


def get_cohere_embeddings_definition():
    from langchain.embeddings import CohereEmbeddings

    return CohereEmbeddings(
        model=os.getenv("COHERE_MODEL_NAME"), cohere_api_key=os.getenv("COHERE_API_KEY")
    )


def return_relevant_docs(
    query,
    mongo_client,
    emb_definition,
    db_name,
    collection_name,
    index_name,
) -> List[Document]:
    from langchain.vectorstores import MongoDBAtlasVectorSearch

    collection = mongo_client[db_name][collection_name]
    vector_store = MongoDBAtlasVectorSearch(
        collection=collection,
        embedding=emb_definition,
        index_name=index_name,
    )
    return vector_store.similarity_search(query)


def add_docs(
    docs: List[Document],
    mongo_client,
    emb_definition,
    db_name,
    collection_name,
    index_name,
) -> None:
    from langchain.vectorstores import MongoDBAtlasVectorSearch

    collection = mongo_client[db_name][collection_name]
    MongoDBAtlasVectorSearch.from_documents(
        documents=docs,
        collection=collection,
        embedding=emb_definition,
        index_name=index_name,
    )


def extract_pii(personal_information: str) -> str:
    from langchain.prompts import PromptTemplate
    from langchain.output_parsers import PydanticOutputParser
    from pydantic import BaseModel, Field

    class PIIModel(BaseModel):
        personal_information: str = Field(description="Personal Information")
        answer: str = Field(description="PII info")

    template_str = """
        You are a powerful assistant who extract personal information from a given context. 
        Your job is to understand what personal information are being requested 
        and extract this information from the given context.

        Given the context {context}.
        
        Help me extract the {personal_information} from the context. 

        If there is no context, return None.

        Debit card number or credit card number are 16 digits long, and only this should be returned.
        SSN or social security numbers are 9 digits long.
        Phone Number is a A 10-digit number including area code.
        Date of Birth is The day, month, and year of your birth.
        Identification: A copy of a government-issued ID, such as a driver's license or passport

        Some examples:
        Personal Information: Debit card number
        Answer: 4444444444444444

        Personal Information: Address
        Answer: 711-2880 Nulla St., Mankato, Mississippi 96522

        Personal Information: Email
        Answer: sampleEmail@gmail.com

        Personal Information: Social Security Number
        Answer: 999999999

        Personal Information: Date of birth
        Answer: 1993 June 26

        {format_instructions}
        """
    mongo_client = get_mongo_client()
    emb_definition = get_cohere_embeddings_definition()
    db_name = "langchain_db"
    collection_name = "langchain_col"
    index_name = "emb"
    context = ""
    docs = return_relevant_docs(
        f"What is my {personal_information}?",
        mongo_client,
        emb_definition,
        db_name,
        collection_name,
        index_name,
    )
    if docs:
        context = "\n".join([doc.page_content for doc in docs])
    pii_parser = PydanticOutputParser(pydantic_object=PIIModel)
    prompt = PromptTemplate(
        template=template_str,
        input_variables=["context", "personal_information"],
        partial_variables={"format_instructions": pii_parser.get_format_instructions()},
    )
    _input = prompt.format_prompt(
        context=context, personal_information=personal_information
    )
    model = get_openai_conversation_model()
    output = model(_input.to_string())
    return pii_parser.parse(output)
