#!/usr/bin/env python3

import os
import zlib
from tkinter import filedialog, messagebox
import tkinter as tk


# 14-byte section header marker
HEADER = bytes([
    0x0C, 0x53, 0x79, 0x73, 0x74, 0x65, 0x6D, 0x2E,
    0x49, 0x6E, 0x74, 0x33, 0x32, 0x01
])

# Fixed 23-byte trailer that appears between the name and the header
TRAILER_LEN = 23

# The 5-byte sequence that ends the preamble, right before the length byte
PREAMBLE_TAIL = bytes([0x06, 0x01, 0x00, 0x00, 0x00])

# How many bytes after the header end to scan for zlib magic 78 9C
ZLIB_SEARCH_WINDOW = 64


def find_all(data: bytes, pattern: bytes):
    start = 0
    while True:
        idx = data.find(pattern, start)
        if idx == -1:
            break
        yield idx
        start = idx + 1


def read_filename(data: bytes, header_pos: int):

    trailer_start = header_pos - TRAILER_LEN
    if trailer_start < len(PREAMBLE_TAIL) + 1:
        return None

    pt_pos = data.rfind(PREAMBLE_TAIL, 0, trailer_start)
    if pt_pos == -1:
        return None

    length_pos = pt_pos + len(PREAMBLE_TAIL)
    length = data[length_pos]
    if length == 0:
        return None

    name_start = length_pos + 1
    name_end   = name_start + length
    if name_end > trailer_start:
        return None 

    try:
        return data[name_start:name_end].decode("utf-8")
    except UnicodeDecodeError:
        return None


def find_zlib_start(data: bytes, search_from: int):
    window = data[search_from: search_from + ZLIB_SEARCH_WINDOW]
    idx = window.find(b'\x78\x9c')
    return None if idx == -1 else search_from + idx


def decompress_section(data: bytes, header_pos: int):
    """
    Find and decompress the zlib stream after the header.
    Returns (zlib_offset, decompressed_bytes).
    """
    zlib_offset = find_zlib_start(data, header_pos + len(HEADER))
    if zlib_offset is None:
        raise ValueError(
            f"No zlib magic (78 9C) found within {ZLIB_SEARCH_WINDOW} bytes "
            f"after header at offset {header_pos:#x}"
        )
    try:
        decompressed = zlib.decompress(data[zlib_offset:])
    except zlib.error as exc:
        raise ValueError(f"zlib decompression failed: {exc}") from exc
    return zlib_offset, decompressed


def unpack(input_path: str, output_dir: str) -> None:
    with open(input_path, "rb") as fh:
        data = fh.read()

    positions = list(find_all(data, HEADER))
    if not positions:
        print("No sections found — header marker not present in file.")
        return

    print(f"Found {len(positions)} section(s) in '{input_path}'\n")

    # First pass: decompress all entries
    entries = []  # list of (filename, decompressed_bytes)
    for i, pos in enumerate(positions):
        print(f"  [{i + 1}/{len(positions)}]  Header offset: {pos:#010x}")

        filename = read_filename(data, pos)
        if filename is None:
            filename = f"section_{i + 1}.bin"
            print(f"    Filename : (unknown) → '{filename}'")
        else:
            print(f"    Filename : {filename}")

        try:
            zlib_offset, decompressed = decompress_section(data, pos)
        except ValueError as exc:
            print(f"    [!] Skipping: {exc}\n")
            continue

        print(f"    zlib at          : {zlib_offset:#010x}")
        print(f"    Decompressed size: {len(decompressed)} bytes")
        entries.append((filename, decompressed))

    groups: dict[str, list[bytes]] = {}
    order:  list[str] = []
    for filename, chunk in entries:
        if filename not in groups:
            groups[filename] = []
            order.append(filename)
        groups[filename].append(chunk)

    # Write output files
    print()
    written = 0
    for filename in order:
        chunks = groups[filename]

        safe_rel = os.path.normpath(filename).lstrip(os.sep)
        out_path  = os.path.join(output_dir, safe_rel)
        os.makedirs(os.path.dirname(out_path) or output_dir, exist_ok=True)

        with open(out_path, "wb") as fh:
            for chunk in chunks:
                fh.write(chunk)

        total = sum(len(c) for c in chunks)
        note  = f"  ← {len(chunks)} entries merged" if len(chunks) > 1 else ""
        print(f"  Saved: {out_path}  [{total} bytes]{note}")
        written += 1

    print(f"\nDone — {written} file(s) written to '{output_dir}/'")



def run_unpack():
    input_file = filedialog.askopenfilename(title="Select input file")
    
    if not input_file:
        return  # User canceled

    output_directory = input_file + "_unpacked"

    try:
        unpack(input_file, output_directory)
        messagebox.showinfo("Success", f"Unpacked to:\n{output_directory}")
    except Exception as e:
        messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    root.title("subnautica PS4 save unpacker")
    root.geometry("300x150")

    btn = tk.Button(root, text="Select File & Unpack", command=run_unpack)
    btn.pack(expand=True)

    root.mainloop()