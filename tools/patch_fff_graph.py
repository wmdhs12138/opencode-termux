#!/usr/bin/env python3
"""Make the bundled FFF wrapper safe for Android AArch64 tagged pointers.

Bun's `read.ptr()` exposes an address as a JavaScript number. Bionic may put an
allocation tag in the top byte, making that representation lossy. The official
FFF wrapper is minified in OpenCode's standalone graph, so this applies a
version-checked transformation that keeps native addresses as bigint values.
"""

from __future__ import annotations

import argparse
import json

from graph_format import Graph, GraphError


def replace_exact(text: str, old: str, new: str, expected: int = 1) -> str:
    count = text.count(old)
    if count != expected:
        raise GraphError(
            f"FFF wrapper pattern count mismatch: expected {expected}, got {count}: {old[:100]!r}"
        )
    return text.replace(old, new)


def patch_wrapper(source: bytes) -> bytes:
    text = source.decode("utf-8")

    text = replace_exact(text, "Z.ptr(", "Z.u64(", 27)
    text = replace_exact(
        text,
        "function I(Q){if(Q===null||Q===0)return null;",
        "function I(Q){if(Q===null||Q===0||Q===0n)return null;",
    )
    text = replace_exact(
        text,
        'if(_.symbols.fff_free_result(V0),!H0||H0===0)return o("fff_create_instance_with returned null handle");',
        'if(_.symbols.fff_free_result(V0),H0===0n)return o("fff_create_instance_with returned null handle");',
    )
    text = replace_exact(text, "$.handlePtr===0", "$.handlePtr===0n", 6)
    text = replace_exact(text, "q+B*oQ", "q+BigInt(B*oQ)")
    text = replace_exact(text, "G+B*J5", "G+BigInt(B*J5)")
    text = replace_exact(text, "W+k*z8", "W+BigInt(k*z8)")
    text = replace_exact(text, "A+u*t5", "A+BigInt(u*t5)")
    text = replace_exact(
        text,
        "function r1(Q,$){if($===0||Q===0)return[];",
        "function r1(Q,$){if($===0||Q===0n)return[];",
    )

    old_dir = (
        "q=F(),G=[],j=[];for(let k=0;k<K;k++){let y=q.symbols."
        "fff_dir_search_result_get_item(W,k);if(y!==null&&y!==0)G.push(Y5(y));"
        "let A=q.symbols.fff_dir_search_result_get_score(W,k);if(A!==null&&A!==0)"
        "j.push(m1(A))}"
    )
    new_dir = (
        "q=F(),B=Z.u64(W,0),u=Z.u64(W,8),G=[],j=[];for(let k=0;k<K;k++){"
        "if(B!==0n)G.push(Y5(B+BigInt(k*24)));if(u!==0n)j.push(m1(u+BigInt(k*J5)))}"
    )
    text = replace_exact(text, old_dir, new_dir)

    old_mixed = (
        "let k=F(),y=[],A=[];for(let B=0;B<K;B++){let u=k.symbols."
        "fff_mixed_search_result_get_item(W,B);if(u!==null&&u!==0)y.push(N5(u));"
        "let _=k.symbols.fff_mixed_search_result_get_score(W,B);if(_!==null&&_!==0)"
        "A.push(m1(_))}"
    )
    new_mixed = (
        "let k=F(),d=Z.u64(W,0),V0=Z.u64(W,8),y=[],A=[];for(let B=0;B<K;B++){"
        "if(d!==0n)y.push(N5(d+BigInt(B*80)));if(V0!==0n)A.push(m1(V0+BigInt(B*J5)))}"
    )
    text = replace_exact(text, old_mixed, new_mixed)

    return text.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--report")
    args = parser.parse_args()

    graph = Graph.from_path(args.input)
    matches = [
        module
        for module in graph.modules()
        if module.name.endswith(b".js")
        and b"fff_create_instance_with" in module.contents
        and b"fff_search_directories" in module.contents
    ]
    if len(matches) != 1:
        raise GraphError(f"expected one bundled FFF wrapper, found {len(matches)}")

    target = matches[0]
    replacement = patch_wrapper(target.contents)
    result = graph.replace_contents_by_append(target.index, replacement)
    result["patch"] = "android-aarch64-tagged-pointers"
    graph.write(args.output)

    encoded = json.dumps(result, indent=2) + "\n"
    if args.report:
        with open(args.report, "w", encoding="utf-8") as stream:
            stream.write(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
