from typing import Callable
from colorama import color_text

def echo(msg: str) -> None:
    print(color_text(msg, "blue"))

def command(func: Callable[..., None]) -> Callable[..., None]:
    # Extremely tiny "decorator" to mimic click.command()
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

def type_error() -> None:
    print(color_text("Number of logs", "blue") + 5) # pyrefly: ignore remove this comment to get a type error
