import os
from langchain.agents import AgentType
from langchain.agents import initialize_agent
from langchain.agents.agent_toolkits.github.toolkit import GitHubToolkit
from langchain.llms import OpenAI
from langchain.utilities.github import GitHubAPIWrapper

# Set your environment variables using os.environ
os.environ["GITHUB_APP_ID"] = "123456"
os.environ["GITHUB_APP_PRIVATE_KEY"] = "path/to/your/private-key.pem"
os.environ["GITHUB_REPOSITORY"] = "username/repo-name"
os.environ["GITHUB_BRANCH"] = "bot-branch-name"
os.environ["GITHUB_BASE_BRANCH"] = "main"

# This example also requires an OpenAI API key
os.environ["OPENAI_API_KEY"] = ""

llm = OpenAI(temperature=0)
github = GitHubAPIWrapper()
toolkit = GitHubToolkit.from_github_api_wrapper(github)
agent = initialize_agent(
    toolkit.get_tools(), llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True
)

agent.run(
    "You have the software engineering capabilities of a Google Principle engineer. You are tasked with completing issues on a github repository. Please look at the existing issues and complete them."
)
