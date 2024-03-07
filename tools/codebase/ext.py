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
SCRIPT_DIR: Path = Path(__file__).resolve().parent


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
    input_folder: Path
    output_folder: Path
    in_header: Path
    in_body: Path
    out_header: Path
    out_body: Path


def main() -> None:
    args = parse_args()

    init_crc_table()
    init_hashes()

    # Logic to update hashes if specified
    if args.update_hashes is not False:
        print("Updating hashes.json")
        update_hashes(args.update_hashes)

    if args.extract:
        print(f"Extracting {args.in_body.name} to {args.output_folder.as_posix()}...")
        extract(args.output_folder, args.in_header, args.in_body)

    if args.create:
        print("Not implemented yet")
        # print(f"Creating from {args.folder_path.as_posix()}...")
        # create(args.header_path, args.body_path, args.folder_path)

    if args.overlay:
        print(f"Updating {args.in_body.name} with {args.input_folder.as_posix()}...")
        overlay(args.input_folder, args.in_header, args.in_body, args.out_header, args.out_body)


def init_hashes() -> None:
    global NAME_HASH

    try:
        with open(SCRIPT_DIR / "hashes.json", "r", encoding="utf8") as file:
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
        if line:
            NAME_HASH[calc_crc(line)] = line

    with open(SCRIPT_DIR / "hashes.json", "w", encoding="utf8") as f:
        f.write(json.dumps(NAME_HASH, indent=4))


def extract(out_path: Path, brh_path: Path, brp_path: Path) -> None:
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


def overlay(
    in_path: Path, brh_path: Path, brp_path: Path, out_brh: Path, out_brp: Path
) -> None:
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

    out_brh.parent.mkdir(exist_ok=True, parents=True)
    out_brp.parent.mkdir(exist_ok=True, parents=True)

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
                blob = og_brp.read((file.size + (LBA_SIZE - 1)) & -LBA_SIZE)

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
        const=f"{SCRIPT_DIR}/paths.txt",
        default=False,
        metavar="paths_file",
        help="Update hashes.",
        type=file_chk,
    )
    group.add_argument(
        "--extract",
        action="store_true",
        help="Extract BRP/BRH pair content. Uses hashes.json if available.",
    )
    group.add_argument(
        "--create",
        action="store_true",
        help="Create BRP/BRH pair from folder.",
    )
    group.add_argument(
        "--overlay",
        action="store_true",
        help="Update BRP/BRH pair from folder of changed files.",
    )

    # Define additional arguments for --header-path and --body-path
    parser.add_argument(
        "--in-header",
        help="Path to header content. Required if --extract or --overlay is specified.",
    )
    parser.add_argument(
        "--in-body",
        help="Path to body content. Required if --extract or --overlay is specified.",
    )

    parser.add_argument(
        "--input-folder",
        help="Path to the folder for creation (--create) or overlaying (--overlay).",
    )

    parser.add_argument(
        "--out-header",
        help="Path to resulting BRH file. Only used if --create or --overlay is specified.",
    )
    parser.add_argument(
        "--out-body",
        help="Path to resulting BRP file. Only used if --create or --overlay is specified.",
    )
    parser.add_argument(
        "--output-folder",
        help="Path to the folder where the BRH/BRP content will be extracted to. Used with --extract",
    )

    # Parse the arguments
    args = parser.parse_args(namespace=Namespace())

    # Extra validation
    if args.extract:
        if not args.in_header:
            parser.error("--extract expects --in-header")
        if not args.in_body:
            parser.error("--extract expects --in-body")
        if not args.output_folder:
            parser.error("--extract expects --output-folder")
        args.in_header = file_chk(args.in_header)
        args.in_body = file_chk(args.in_body)
        args.output_folder = dir_create(args.output_folder)

    if args.overlay:
        if not args.in_header:
            parser.error("--overlay expects --in-header")
        if not args.in_body:
            parser.error("--overlay expects --in-body")
        if not args.out_header:
            parser.error("--overlay expects --out-header")
        if not args.out_body:
            parser.error("--overlay expects --out-body")
        if not args.input_folder:
            parser.error("--overlay expects --input-folder")
        args.in_header = file_chk(args.in_header)
        args.in_body = file_chk(args.in_body)
        args.out_header = Path(args.out_header).absolute()
        args.out_body = Path(args.out_body).absolute()
        args.input_folder = dir_chk(args.input_folder)

    return args


def dir_create(path: str) -> Path:
    p = Path(path).absolute()
    if p.is_dir():
        return p
    else:
        p.mkdir(exist_ok=True, parents=True)


def dir_chk(path: str) -> Path:
    p = Path(path).absolute()
    if p.is_dir():
        return p
    else:
        raise argparse.ArgumentTypeError(f'"{p}" is not a folder!')


def file_chk(path: str) -> Path:
    p = Path(path).absolute()
    if p.is_file():
        return p
    else:
        raise argparse.ArgumentTypeError(f'"{p}" is not a file!')


if __name__ == "__main__":
    main()
