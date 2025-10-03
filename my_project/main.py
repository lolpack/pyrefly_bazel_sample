from click import echo, command

@command
def main() -> None:
    echo("Hello from my_project!")

if __name__ == "__main__":
    main()
