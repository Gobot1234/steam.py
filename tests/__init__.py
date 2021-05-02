import os

USERNAME: str = os.getenv("USERNAME")
PASSWORD: str = os.getenv("PASSWORD")
SHARED_SECRET: str = os.getenv("SHARED_SECRET")
IDENTITY_SECRET: str = os.getenv("IDENTITY_SECRET")
RUNNING_AS_ACTION: bool = os.getenv("GITHUB_ACTIONS").lower() == "true"
