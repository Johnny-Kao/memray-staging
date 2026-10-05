#!/usr/bin/env python3
import argparse
import gc
import json
import os
import statistics
import tempfile
import time

from memray import AllocatorType
from memray._memray import RecordWriterTestHarness


CASES = {
    "hit_common": {
        "native_traces": False,
        "allocator": AllocatorType.MALLOC,
        "reuse_address": True,
        "size": 1234,
        "native_frame_id": 0,
    },
    "miss_common": {
        "native_traces": False,
        "allocator": AllocatorType.MALLOC,
        "reuse_address": False,
        "size": 1234,
        "native_frame_id": 0,
    },
    "hit_uncommon": {
        "native_traces": False,
        "allocator": AllocatorType.POSIX_MEMALIGN,
        "reuse_address": True,
        "size": 1234,
        "native_frame_id": 0,
    },
    "hit_native": {
        "native_traces": True,
        "allocator": AllocatorType.MALLOC,
        "reuse_address": True,
        "size": 1234,
        "native_frame_id": 1 << 20,
    },
    "hit_free": {
        "native_traces": False,
        "allocator": AllocatorType.PYMALLOC_FREE,
        "reuse_address": True,
        "size": 0,
        "native_frame_id": 0,
    },
}


def run_once(case, count):
    fd, path = tempfile.mkstemp(prefix="memray-m02-", suffix=".bin")
    os.close(fd)
    try:
        writer = RecordWriterTestHarness(path, native_traces=case["native_traces"])
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            start = time.perf_counter_ns()
            ok = writer.benchmark_allocation_records(
                count,
                1,
                0x10000000,
                case["size"],
                case["allocator"],
                case["native_frame_id"],
                case["reuse_address"],
            )
            elapsed = time.perf_counter_ns() - start
        finally:
            if gc_was_enabled:
                gc.enable()
        if not ok:
            raise RuntimeError("writer benchmark failed")
        if not writer.write_trailer():
            raise RuntimeError("failed to write trailer")
        del writer
        size = os.path.getsize(path)
        return elapsed / count, size
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1_000_000)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--case", choices=["all", *CASES], default="all")
    args = parser.parse_args()

    selected = CASES if args.case == "all" else {args.case: CASES[args.case]}
    result = {}

    for name, case in selected.items():
        for _ in range(args.warmups):
            run_once(case, args.count)

        timings = []
        sizes = []
        for _ in range(args.repetitions):
            ns_per_record, capture_size = run_once(case, args.count)
            timings.append(ns_per_record)
            sizes.append(capture_size)

        result[name] = {
            "count": args.count,
            "repetitions": args.repetitions,
            "median_ns_per_record": statistics.median(timings),
            "min_ns_per_record": min(timings),
            "max_ns_per_record": max(timings),
            "raw_ns_per_record": timings,
            "capture_sizes": sizes,
        }

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
