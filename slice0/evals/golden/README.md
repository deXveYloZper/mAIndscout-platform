# Golden fixtures — 2026-09 folder

Source PDFs live in `/home/workdir/attachments/`.  
These JSON files are the expected *decisions*, not a full claim dump. An extractor may produce more claims; it must not violate `must` / `must_not`.

Eval harness (later): load PDF → process_document → assert flags and key payloads.
