import sys


def main() -> None:
    # The packaged macOS app has a single executable, so it also serves the console utilities
    # and the check of the Apple Silicon speech engine, which runs in a process of its own.
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from .cli import main as cli_main
        del sys.argv[1]
        cli_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--probe-mlx":
        from .mac.transcriber import probe
        sys.exit(probe())
    from .app import run
    sys.exit(run(sys.argv))


if __name__ == "__main__":
    main()
