"""Entry point of the packaged macOS app."""
import multiprocessing

from susurros.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
