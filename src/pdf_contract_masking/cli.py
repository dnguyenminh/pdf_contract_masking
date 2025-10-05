from __future__ import annotations
import argparse
from .utils import mask_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf-mask", description="Mask text except last N characters")
    parser.add_argument("text", help="Text to mask")
    parser.add_argument("--keep-last", type=int, default=4, help="Number of characters to keep at the end")
    args = parser.parse_args(argv)
    print(mask_text(args.text, keep_last=args.keep_last))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
