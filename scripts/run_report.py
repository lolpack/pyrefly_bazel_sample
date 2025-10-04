from click import command, echo
from plugins import summarize


@command
def main() -> None:
    echo(summarize(["daily", "weekly", "monthly"]))


if __name__ == "__main__":
    main()
