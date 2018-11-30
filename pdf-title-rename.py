#!/usr/bin/env python3

"""
A script to batch rename PDF files based on metadata/XMP title and author

Requirements:
    - PDFMiner: https://github.com/euske/pdfminer/
    - xmp: lightweight XMP parser from
        http://blog.matt-swain.com/post/25650072381/
            a-lightweight-xmp-parser-for-extracting-pdf-metadata-in
"""


NAME = "pdf-title-rename"
VERSION = "0.0.3"
DATE = "2017-07-15"


import argparse
import os
import subprocess
import sys

# PDF and metadata libraries
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser, PDFSyntaxError
from pdfminer.pdftypes import resolve1

from xmp import xmp_to_dict


class RenamePDFsByTitle(object):

    """
    This class parses PDF files for title and author and then
    renames them.
    """

    def __init__(self, args):
        self.pdf_files = args.files
        self.dry_run = args.dry_run
        self.interactive = args.interactive
        self.destination = None
        if args.destination:
            if os.path.isdir(args.destination):
                self.destination = args.destination
            else:
                print("warning: destination is not a valid directory")

    def main(self):
        """Entry point for running the script."""
        Ntot = len(self.pdf_files)
        Nrenamed = 0
        Nfiled = 0
        Nmissing = 0
        Nerrors = 0

        for f in self.pdf_files:
            root, ext = os.path.splitext(f)
            path, base = os.path.split(root)
            print(f'Processing "{f}":')

            # Parse standard and XMP metadata, then go interactive if specified
            title, author = self._get_info(f)

            # Reuse the base filename if there is an author but no title
            if author and not title:
                title = base

            if not (author or title):
                print(" -- Could not find metadata in the file")
                Nmissing += 1
                continue

            newf = os.path.join(path, self._new_filename(title, author))
            print(f' -- Renaming to "{newf}"')
            if self.dry_run:
                continue

            try:
                os.rename(f, newf)
            except OSError:
                print(" -- Error renaming file, maybe it moved?")
                Nerrors += 1
                continue
            else:
                Nrenamed += 1

            if self.destination:
                if subprocess.call(["mv", newf, self.destination]) == 0:
                    print(" -- Filed to", self.destination)
                    Nfiled += 1
                else:
                    print(" -- Error moving file")
                    Nerrors += 1

        if self.dry_run:
            print(f"Processed {Ntot} files [dry run]:")
        else:
            print(f"Processed {Ntot} files:")
        print(f" - Renamed: {Nrenamed}")
        if self.destination:
            print(f" - Filed: {Nfiled}")
        print(f" - Missing metadata: {Nmissing}")
        print(f" - Errors: {Nerrors}")

        return 0

    def _new_filename(self, title, author):
        n = self._sanitize(title)
        if author:
            n = " - ".join((self._sanitize(author), n))
        n = f"{n[:250]}.pdf"  # limit filenames to ~255 chars
        return n

    def _sanitize(self, s):
        keep = [" ", ".", "_", "-", "\u2014"]
        return "".join(c for c in s if c.isalnum() or c in keep).strip()

    def _get_info(self, fn):
        title = author = None

        with open(fn, "rb") as pdf:
            info = self._get_metadata(pdf)

            if "Title" in info:
                ti = self._resolve_objref(info["Title"])
                try:
                    title = ti.decode("utf-8")
                except AttributeError:
                    pass
                except UnicodeDecodeError:
                    print(f" -- Could not decode title bytes: {repr(ti)}")

            if "Author" in info:
                au = self._resolve_objref(info["Author"])
                try:
                    author = au.decode("utf-8")
                except AttributeError:
                    pass
                except UnicodeDecodeError:
                    print(f" -- Could not decode author bytes: {repr(au)}")

            if "Metadata" in self.doc.catalog:
                xmpt, xmpa = [self._resolve_objref(x) for x in self._get_xmp_metadata()]
                if xmpt:
                    title = xmpt
                if xmpa:
                    author = xmpa

        if type(title) is str:
            title = title.strip()
            if title.lower() == "untitled":
                title = None

        if self.interactive:
            title, author = self._interactive_info_query(fn, title, author)

        return title, author

    def _resolve_objref(self, ref):
        if hasattr(ref, "resolve"):
            return ref.resolve()
        return ref

    def _interactive_info_query(self, fn, t, a):
        def ri(p):
            return input(p).lower().strip()

        print("-" * 60)
        print("Filename:".ljust(20), fn)
        print(" * Found (t)itle:".ljust(20), f'"{str(t)}"')
        print(" * Found (a)uthors:".ljust(20), f'"{str(a)}"')

        ans = ri("Change (t/a) or open (o) or keep (k)? (t/a/o/k) ")
        while ans != "k":
            if ans == "t":
                t = input("New title: ").strip()
            elif ans == "a":
                a = input("New author string: ").strip()
            elif ans == "o":
                subprocess.call(["open", fn])
            else:
                print("Bad option, please choose again:")
            ans = ri("(t/a/o/k) ")
        return t, a

    def _get_metadata(self, h):
        parser = PDFParser(h)
        try:
            doc = self.doc = PDFDocument(parser)
        except PDFSyntaxError:
            return {}
        parser.set_document(doc)

        if not hasattr(doc, "info") or len(doc.info) == 0:
            return {}
        return doc.info[0]

    def _get_xmp_metadata(self):
        t = a = None
        metadata = resolve1(self.doc.catalog["Metadata"]).get_data()
        try:
            md = xmp_to_dict(metadata)
        except:
            return t, a

        try:
            t = md["dc"]["title"]["x-default"]
        except KeyError:
            pass

        try:
            a = md["dc"]["creator"]
        except KeyError:
            pass
        else:
            if type(a) is bytes:
                a = a.decode("utf-8")
            if type(a) is str:
                a = [a]
            a = list(filter(bool, a))  # remove None, empty strings, ...
            if len(a) > 1:
                a = " ".join((self._au_last_name(a[0]), self._au_last_name(a[-1])))
            elif len(a) == 1:
                a = self._au_last_name(a[0])
            else:
                a = None

        return t, a

    def _au_last_name(self, name):
        return name.split()[-1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF batch rename")
    parser.add_argument("files", nargs="+", help="list of pdf files to rename")
    parser.add_argument(
        "-n",
        dest="dry_run",
        action="store_true",
        help="dry-run listing of filename changes",
    )
    parser.add_argument(
        "-i", dest="interactive", action="store_true", help="interactive mode"
    )
    parser.add_argument(
        "-d", "--dest", dest="destination", help="destination folder for renamed files"
    )
    args = parser.parse_args()
    sys.exit(RenamePDFsByTitle(args).main())
