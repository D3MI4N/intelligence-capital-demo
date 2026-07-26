"""Ingest pipeline: parse the wiki into chunks, then derive the indexes.

The markdown files are the primary store. Everything under .index/ is derived
and disposable - ingest/rebuild.sh regenerates all of it from the files.
"""
