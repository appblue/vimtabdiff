#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import sys
import argparse
import itertools
import tempfile
import subprocess
import shlex
from pathlib import Path
from typing import TypeVar
from collections.abc import Iterator, Callable

R = TypeVar('R')


def star(f: Callable[..., R]) -> Callable[[tuple], R]:
    """ see https://stackoverflow.com/q/21892989 """
    return lambda args: f(*args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show diff of files from two directories in vim tabs",
        epilog="See https://github.com/balki/vimtabdiff for more info")
    parser.add_argument("pathA", type=Path)
    parser.add_argument("pathB", type=Path)
    parser.add_argument("--vim", help="vim command to run", default="vim")
    parser.add_argument("--exclude", help="comma separated list of files/folders to exclude (e.g. .git)", default=None)
    parser.add_argument("--git", help="add **/.git to exclusion list", action="store_true")
    parser.add_argument("--onlydiffs", help="only open files where there is a diff", action="store_true")
    parser.add_argument(
        "--dry", help="only print the vim script to execute", action="store_true"
    )
    return parser.parse_args()


def get_dir_info(dirpath: Path | None, exclude: list[str]) -> tuple[list[Path], list[Path]]:
    if not dirpath:
        return [], []
    dirs, files = [], []
    for p in dirpath.iterdir():
        if any( (p.full_match(e) for e in exclude) ):
            if p.is_dir():
                dirs.append(p)
            else:
                files.append(p)
    return dirs, files


def get_pairs(aPaths: list[Path],
              bPaths: list[Path]) -> Iterator[tuple[Path | None, Path | None]]:
    aItems = [(item, 'A') for item in aPaths]
    bItems = [(item, 'B') for item in bPaths]
    abItems = aItems + bItems
    abItems.sort(key=star(lambda item, tag: (item.name, tag)))
    for _, items in itertools.groupby(abItems,
                                      key=star(lambda item, _: item.name)):
        match list(items):
            case [(aItem, _), (bItem, _)]:
                yield aItem, bItem
            case [(item, 'A'),]:
                yield item, None
            case [(item, 'B'),]:
                yield None, item


def get_file_pairs(
        a: Path | None,
        b: Path | None,
        exclude: list[str]) -> Iterator[tuple[Path | None, Path | None]]:
    aDirs, aFiles = get_dir_info(a, exclude)
    bDirs, bFiles = get_dir_info(b, exclude)
    yield from get_pairs(aFiles, bFiles)
    for aDir, bDir in get_pairs(aDirs, bDirs):
        yield from get_file_pairs(aDir, bDir, exclude)


def main() -> None:
    args = parse_args()

    excludeList = []
    if args.git:
        excludeList.append('**/.git')

    if args.exclude:
        for p in args.exclude.split(','):
            excludeList.append(p)

    vimCmdFile = tempfile.NamedTemporaryFile(mode='w', delete=False)
    with vimCmdFile:
        cmds = f"""
        let s:spr = &splitright
        set splitright
        """
        print(cmds, file=vimCmdFile)
        for a, b in get_file_pairs(args.pathA, args.pathB, excludeList):
            aPath = a.resolve() if a else args.pathA.joinpath(b.relative_to(args.pathB)).resolve() # os.devnull
            bPath = b.resolve() if b else args.pathB.joinpath(a.relative_to(args.pathA)).resolve() # os.devnull
            if (
                args.onlydiffs
                and a and b
                and open(aPath, mode="rb").read() == open(bPath, mode="rb").read()
            ):
                continue
            print(f"tabedit {aPath} | vsp {bPath}", file=vimCmdFile)
        cmds = f"""
        let &splitright = s:spr
        tabdo windo :1
        tabdo windo diffthis
        tabdo windo diffupdate
        tabfirst | tabclose
        call delete("{vimCmdFile.name}")
        """

        print(cmds, file=vimCmdFile)
    if not args.dry:
        subprocess.run(shlex.split(args.vim) + ["-S", vimCmdFile.name])
    else:
        with open(vimCmdFile.name) as f:
            for l in f:
                print(l.rstrip())


if __name__ == '__main__':
    main()
