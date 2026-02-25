def __init__(self):
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Set it in your environment or .env file before starting the app."
        )

    self.client = AsyncOpenAI(api_key=api_key)

    self.model = "gpt-4o-mini"
    self.temperature = 0.0
    self.max_tokens = 1000
    self.timeout_seconds = 30
    self.max_retries = 2

    self.encoding = get_encoding("cl100k_base")
