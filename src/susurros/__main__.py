import sys


def main() -> None:
    from .app import run
    sys.exit(run(sys.argv))


if __name__ == "__main__":
    main()
