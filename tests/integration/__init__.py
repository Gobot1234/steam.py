import os

USERNAME = os.environ["USERNAME"]
PASSWORD = os.environ["PASSWORD"]
SHARED_SECRET = os.environ["SHARED_SECRET"]
IDENTITY_SECRET = os.environ["IDENTITY_SECRET"]
RUNNING_AS_ACTION: bool = os.getenv("GITHUB_ACTIONS", "").lower() == "true"
