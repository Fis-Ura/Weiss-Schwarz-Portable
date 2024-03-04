import struct
from pathlib import Path
import argparse
import gzip
from dataclasses import dataclass
import json

CRC_TABLE_SIZE = 256
LBA_SIZE = 0x800
NAME_HASH: dict[int, str] = dict()
crc_table: list[int] = []


@dataclass
class BrFile:
    name_hash: int
    offset: int
    size: int
    content_hash: int


class Namespace(argparse.Namespace):
    update_hashes: bool
    extract: bool
    create: bool
    overlay: bool
    paths_file: Path
    folder_path: Path
    header_path: Path
    body_path: Path


def main():
    args = parse_args()

    init_crc_table()
    init_hashes()

    # Logic to update hashes if specified
    if args.update_hashes is not False:
        print("Updating hashes.json")
        update_hashes(args.update_hashes)

    if args.extract:
        print(f"Extracting {args.body_path.name} to {args.folder_path.as_posix()}...")
        extract(args.header_path, args.body_path, args.folder_path)

    if args.create:
        print("Not implemented yet")
        # print(f"Creating from {args.folder_path.as_posix()}...")
        # create(args.header_path, args.body_path, args.folder_path)

    if args.overlay:
        print(f"Updating {args.body_path.name} with {args.folder_path.as_posix()}...")
        overlay(args.header_path, args.body_path, args.folder_path)


def init_hashes() -> None:
    global NAME_HASH

    try:
        with open("hashes.json", "r", encoding="utf8") as file:
            NAME_HASH = json.load(
                file,
                object_pairs_hook=lambda pairs: {
                    int(key): value for key, value in pairs
                },
            )
    except FileNotFoundError:
        pass


def update_hashes(paths: Path) -> None:
    global NAME_HASH

    with open(paths, "r", encoding="utf8") as f:
        lines = f.read().split("\n")

    for line in lines:
        NAME_HASH[calc_crc(line)] = line

    with open("hashes.json", "w", encoding="utf8") as f:
        f.write(json.dumps(NAME_HASH, indent=4))


def extract(brh_path: Path, brp_path: Path, out_path: Path) -> None:
    out_path.mkdir(parents=True, exist_ok=True)

    with open(brh_path, "rb") as header:
        count_1, _ = struct.unpack("<2I", header.read(8))
        hashes = struct.unpack(f"<{count_1}I", header.read(count_1 * 4))
        offsets = struct.unpack(f"<{count_1}I", header.read(count_1 * 4))
        sizes = struct.unpack(f"<{count_1}I", header.read(count_1 * 4))
        # chksums = struct.unpack(f"<{count_1}I", header.read(count_1 * 4))

    with open(brp_path, "rb") as body:
        for i in range(count_1):
            hash = hashes[i]
            off = offsets[i]
            body.seek(off)
            if hash in NAME_HASH:
                p = out_path / NAME_HASH[hash]
                p.parent.mkdir(parents=True, exist_ok=True)
            else:
                p = out_path / f"UNKNOWN/${hash:08X}"
                p.parent.mkdir(parents=True, exist_ok=True)

            blob = body.read(sizes[i])
            if blob[:2] == b"\x1f\x8b":
                p = p.with_name(f"#{p.name}")
                blob = gzip.decompress(blob)

            print(f"Extracting {p.relative_to(out_path)}")
            with open(p, "wb") as f:
                f.write(blob)


def overlay(brh_path: Path, brp_path: Path, in_path: Path) -> None:
    out_brh: Path = brh_path.with_name(f"NEW_{brh_path.name}")
    out_brp: Path = brp_path.with_name(f"NEW_{brp_path.name}")

    input_files: dict[int, Path] = dict()

    for p in in_path.rglob("*"):
        if p.is_dir():
            continue
        p = p.relative_to(in_path)
        if p.name.startswith("$"):
            input_files[int(p.name[1:], 16)] = p
        if p.name.startswith("#$"):
            input_files[int(p.name[2:], 16)] = p
        if p.name.startswith("#"):
            input_files[calc_crc(p.as_posix().replace("#", ""))] = p
        else:
            input_files[calc_crc(p.as_posix())] = p

    with open(brh_path, "rb") as header:
        count_1, _ = struct.unpack("<2I", header.read(8))
        nhs = struct.unpack(f"<{count_1}I", header.read(count_1 * 4))
        off = struct.unpack(f"<{count_1}I", header.read(count_1 * 4))
        sze = struct.unpack(f"<{count_1}I", header.read(count_1 * 4))
        chs = struct.unpack(f"<{count_1}I", header.read(count_1 * 4))

    files: list[BrFile] = []
    for i in range(count_1):
        files.append(BrFile(nhs[i], off[i], sze[i], chs[i]))

    files.sort(key=lambda x: x.offset)

    with open(out_brp, "wb") as brp, open(brp_path, "rb") as og_brp:
        for file in files:
            if file.name_hash in input_files:
                fp = in_path / input_files[file.name_hash]
                with open(fp, "rb") as f:
                    blob = f.read()

                if fp.name.startswith("#"):
                    blob = gzip.compress(blob)
                file.size = len(blob)
                n_pad = (LBA_SIZE - (len(blob) % LBA_SIZE)) % LBA_SIZE
                blob = blob + b"\x00" * n_pad
                file.content_hash = calc_crc(blob)
            else:
                og_brp.seek(file.offset)
                blob = og_brp.read((file.size + (LBA_SIZE-1)) & -LBA_SIZE)

            file.offset = brp.tell()
            brp.write(blob)
            assert (brp.tell() % LBA_SIZE) == 0

    files.sort(key=lambda x: x.name_hash)

    with open(out_brh, "wb") as brh:
        entries = len(files)
        brh.write(struct.pack("<I", entries))
        brh.write(struct.pack("<I", entries))
        brh.write(struct.pack(f"<{entries}I", *[x.name_hash for x in files]))
        brh.write(struct.pack(f"<{entries}I", *[x.offset for x in files]))
        brh.write(struct.pack(f"<{entries}I", *[x.size for x in files]))
        brh.write(struct.pack(f"<{entries}I", *[x.content_hash for x in files]))


def init_crc_table() -> None:
    crc_table.clear()
    for i in range(CRC_TABLE_SIZE):
        temp = i << 24

        for _ in range(8):
            if (temp & 0x80000000) == 0:
                temp <<= 1
            else:
                temp <<= 1
                temp ^= 0x4C11DB7
        crc_table.append(temp)


def calc_crc(input: str | bytes) -> int:
    hash = 0

    if isinstance(input, str):
        input = input.encode()

    for b in input:
        hash = (hash << 8) ^ crc_table[((hash >> 24) & 0xFF) ^ b]

    return ~hash & 0xFFFFFFFF


def parse_args() -> Namespace:
    parser = argparse.ArgumentParser(description="W&S - Portable tool")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--update-hashes",
        nargs="?",
        const="./paths.txt",
        default=False,
        metavar="paths_file",
        help="Update hashes.",
        type=file_path,
    )
    group.add_argument(
        "--extract",
        action="store_true",
        help="Extract content. Optionally specify --header-path, --body-path or --output-folder to specify paths",
    )
    group.add_argument(
        "--create",
        action="store_true",
        help="Create BRP/BRH pair from folder",
    )
    group.add_argument(
        "--overlay",
        action="store_true",
        help="Update BRP/BRH pair from folder of changed files. Optionally specify --header-path, --body-path or --input-folder to specify paths",
    )

    # Define additional arguments for --header-path and --body-path
    parser.add_argument(
        "--header-path",
        default="_FINAL.BRH",
        type=file_path,
        help="Path to header content. Only used if --extract or --insert is specified.",
    )
    parser.add_argument(
        "--body-path",
        default="__FINAL.BRP",
        type=file_path,
        help="Path to body content. Only used if --extract or --insert is specified.",
    )

    parser.add_argument(
        "--input-folder",
        "--output-folder",
        dest="folder_path",
        default="FINAL",
        help="Path to the folder for insertion (for --insert) or extraction (for --extract).",
        type=dir_path,
    )

    # Parse the arguments
    return parser.parse_args(namespace=Namespace())


def dir_path(path: str) -> Path:
    p = Path(path).absolute()
    if p.is_dir():
        return p
    else:
        raise argparse.ArgumentTypeError(f'"{path}" is not a folder!')


def file_path(path: str) -> Path:
    p = Path(path).absolute()
    if p.is_file():
        return p
    else:
        raise argparse.ArgumentTypeError(f'"{path}" is not a file!')


if __name__ == "__main__":
    main()
