from click import command, echo
from services.reporting import build_report


@command
def main() -> None:
    echo(build_report("cli-report"))


if __name__ == "__main__":
    main()
