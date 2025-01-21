#!/usr/bin/env python
import click
import sys

from msg_split import split_message, SplitMessageError

@click.command()
@click.argument("html_file", type=click.File("r"))
@click.option("--max-len", default=4096, help="Максимальная длина фрагмента.")
def main(html_file, max_len):
    """Скрипт читает HTML из файла HTML_FILE и выводит разбиение на фрагменты."""
    source_html = html_file.read().strip()

    try:
        fragments = list(split_message(source_html, max_len=max_len))
    except SplitMessageError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    for i, frag in enumerate(fragments, 1):
        print(f"-- fragment #{i}: {len(frag)} chars --")
        print(frag)

if __name__ == "__main__":
    main()
