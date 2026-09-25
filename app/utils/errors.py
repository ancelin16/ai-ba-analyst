"""Application error types.

Every error carries a `user_message` that is safe and helpful to show in the
UI, separate from technical detail meant for logs.
"""


class AppError(Exception):
    user_message = "Something went wrong. Please try again."

    def __init__(self, detail: str = "", user_message: str | None = None):
        super().__init__(detail or self.user_message)
        self.detail = detail
        if user_message:
            self.user_message = user_message


class InputValidationError(AppError):
    user_message = "Please correct the highlighted input and try again."


class MissingCredentialsError(AppError):
    user_message = (
        "No Anthropic API key found. Add ANTHROPIC_API_KEY to your .env file, "
        "or switch on Demo Mode to explore the pre-generated examples."
    )


class AIResponseError(AppError):
    user_message = (
        "The AI returned a response that did not match the expected structure. "
        "Please try again. If it keeps happening, simplify or shorten the request."
    )


class InsufficientInformationError(AppError):
    user_message = (
        "The request doesn't contain enough information to write meaningful requirements. "
        "Answer the clarifying questions or add detail to the request, then try again."
    )


class AIServiceError(AppError):
    user_message = "The AI service could not be reached. Please try again in a moment."
