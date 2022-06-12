import argparse
from os.path import basename, splitext
from pathlib import Path
from typing import Dict

from relic.sga.errors import FileABC
from relic.sga.apis import read_archive
from scripts.universal.common import PrintOptions, print_error, print_any, SharedExtractorParser
from scripts.universal.sga.common import get_runner


def add_args(parser: argparse.ArgumentParser):
    parser.add_argument("-u", "--unique", action="store_true", help="Include the Archive name in the result path.")


def build_parser():
    parser = argparse.ArgumentParser(prog="Unpack SGA", description="Unpacks an SGA to normal files", parents=SharedExtractorParser)
    add_args(parser)
    return parser


def extract_args(args: argparse.Namespace) -> Dict:
    return {'prepend_archive_path': args.unique}


def unpack_archive(in_path: str, out_path: str, print_opts: PrintOptions = None, prepend_archive_path: bool = True, indent_level: int = 0, **kwargs):
    out_path = Path(out_path)
    with open(in_path, "rb") as in_handle:
        archive = read_archive(in_handle, True)
        archive_name = splitext(basename(in_path))[0]
        # with archive.header.data_ptr.stream_jump_to(in_handle) as data_stream:
        print_any(f"Unpacking \"{archive_name}\"...", indent_level, print_opts)
        for _, _, _, files in archive.walk():
            for file in files:
                file: FileABC
                try:
                    relative_file_path = file.path

                    # Cant use drive since our 'drive' isn't one letter
                    if ':' in relative_file_path.parts[0]:
                        relative_file_path = str(relative_file_path).replace(":", "")  # Valid on windows systems, on posix; idk

                    rel_out_path = Path(out_path)
                    if prepend_archive_path:
                        rel_out_path /= archive_name

                    rel_out_path /= relative_file_path

                    rel_out_path.parent.mkdir(parents=True, exist_ok=True)
                    print_any(f"Reading \"{relative_file_path}\"...", indent_level + 1, print_opts)
                    with open(rel_out_path, "wb") as out_handle:
                        file.read_data(in_handle)
                        out_handle.write(file.data)
                    print_any(f"Writing \"{rel_out_path}\"...", indent_level + 2, print_opts)
                except KeyboardInterrupt:
                    raise
                except BaseException as e:
                    if not print_opts or print_opts.error_fail:
                        raise
                    else:
                        print_error(e, indent_level, print_opts)


Runner = get_runner(unpack_archive, extract_args)
