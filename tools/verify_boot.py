#!/usr/bin/env python3
"""Verify a repacked Android boot image (header v0/v1/v2) against the stock image.

Checks performed:
  * file size matches the boot partition size
  * ANDROID! magic and a sane page size
  * kernel segment is byte-identical to the supplied Image.gz
  * ramdisk segment is byte-identical to the stock image
  * cmdline starts with the stock cmdline, is NUL terminated, and carries
    kernelsu.allow_shell=1

Usage:
  verify_boot.py new-boot.img --stock boot.img --kernel Image.gz \
      --partition-size 100663296
"""
import argparse
import hashlib
import sys
from pathlib import Path

CMD_OFF = 64
CMD_LEN = 512
ALLOW_SHELL = b"kernelsu.allow_shell=1"


def align(value, page):
    return (value + page - 1) // page * page


def parse(path):
    data = Path(path).read_bytes()
    if data[:8] != b"ANDROID!":
        raise SystemExit(f"{path}: not an Android boot image (bad magic)")

    def u32(off):
        return int.from_bytes(data[off:off + 4], "little")

    info = {
        "path": str(path),
        "data": data,
        "size": len(data),
        "kernel_size": u32(8),
        "ramdisk_size": u32(16),
        "second_size": u32(24),
        "page_size": u32(36),
        "header_version": u32(40),
        "cmdline_raw": data[CMD_OFF:CMD_OFF + CMD_LEN],
    }
    cmd = info["cmdline_raw"].split(b"\0", 1)[0]
    info["cmdline"] = cmd
    info["cmdline_terminated"] = (
        len(cmd) < CMD_LEN and info["cmdline_raw"][len(cmd):len(cmd) + 1] == b"\0"
    )
    if info["header_version"] not in (0, 1, 2):
        raise SystemExit(
            f"{path}: unsupported header version {info['header_version']} "
            "(this tool only handles v0/v1/v2)"
        )
    if info["page_size"] < 2048 or info["page_size"] & (info["page_size"] - 1):
        raise SystemExit(f"{path}: bad page size {info['page_size']}")
    return info


def segment(info, off, length):
    return info["data"][off:off + length]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("boot")
    ap.add_argument("--stock")
    ap.add_argument("--kernel")
    ap.add_argument("--partition-size", type=int, default=100663296)
    args = ap.parse_args()

    boot = parse(args.boot)
    page = boot["page_size"]
    kernel_off = page
    ramdisk_off = align(kernel_off + boot["kernel_size"], page)
    second_off = align(ramdisk_off + boot["ramdisk_size"], page)

    errors = []

    def check(cond, msg):
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            errors.append(msg)

    print(f"{args.boot}")
    check(boot["size"] == args.partition_size,
          f"file size {boot['size']} == partition size {args.partition_size} "
          f"({boot['size'] // 1024 // 1024} MiB)")
    check(not boot["size"] % page, "file size is a multiple of the page size")
    print(f"  info header v{boot['header_version']}, page {page}, "
          f"kernel {boot['kernel_size']} B, ramdisk {boot['ramdisk_size']} B")

    if args.kernel:
        image = Path(args.kernel).read_bytes()
        check(boot["kernel_size"] == len(image),
              f"kernel_size {boot['kernel_size']} == {args.kernel} size {len(image)}")
        check(segment(boot, kernel_off, len(image)) == image,
              "kernel segment is byte-identical to Image.gz")

    if args.stock:
        stock = parse(args.stock)
        check(boot["page_size"] == stock["page_size"], "page size matches stock")
        check(boot["header_version"] == stock["header_version"],
              "header version matches stock")
        stock_ramdisk = segment(stock, stock["page_size"] + align(
            stock["kernel_size"], stock["page_size"]), stock["ramdisk_size"])
        check(segment(boot, ramdisk_off, boot["ramdisk_size"]) == stock_ramdisk,
              "ramdisk segment is byte-identical to stock")
        check(boot["cmdline"].startswith(stock["cmdline"]),
              "cmdline starts with the stock cmdline")
        print(f"  info stock cmdline: {stock['cmdline'].decode('ascii', 'replace')}")
        if stock["second_size"]:
            check(boot["second_size"] == stock["second_size"],
                  "second stage size matches stock")

    check(boot["cmdline_terminated"], "cmdline is NUL terminated within 512 bytes")
    check(ALLOW_SHELL in boot["cmdline"].split(),
          "cmdline contains kernelsu.allow_shell=1")
    print(f"  info cmdline: {boot['cmdline'].decode('ascii', 'replace')}")
    print(f"  info sha256: {hashlib.sha256(boot['data']).hexdigest()}")

    if errors:
        print(f"\n{len(errors)} check(s) failed")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
