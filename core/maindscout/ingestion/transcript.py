"""Call transcripts: whatever the call tool exported (.txt, .vtt, .srt, .docx, or pasted text) becomes plain text with
one "Speaker: words" line per turn. Timestamps and cue numbers are dropped; speaker labels are kept, because only the
candidate's own lines may become facts about them."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree

EXTENSIONS = (".txt", ".vtt", ".srt", ".docx")
MAX_CHARS = 200_000  # about three hours of talk

_TIME = re.compile(r"^\s*(\d{1,2}:)?\d{1,2}:\d{2}([.,]\d{1,3})?\s*-->\s*(\d{1,2}:)?\d{1,2}:\d{2}([.,]\d{1,3})?.*$")
_VOICE = re.compile(r"<v(?:\.[\w.-]+)?\s+([^>]+)>(.*?)(?:</v>|$)", re.S)
_TAG = re.compile(r"</?[^>]+>")
# "[Ana Silva] 10:01:22" (Zoom) or "Ana Silva  0:03" / "Ana Silva 00:01:05" (Teams, Meet): a header line, words follow.
_HEADER = re.compile(r"^\s*\[?([^\]\d:][^\]:]{0,60}?)\]?\s+\(?\d{1,2}:\d{2}(:\d{2})?\)?\s*$")
_LABEL = re.compile(r"^([^\s:][^:\n]{0,60}):\s+\S", re.M)
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class TranscriptError(ValueError):
    pass


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as error:
        raise TranscriptError("This .docx could not be opened") from error
    root = ElementTree.fromstring(xml)
    lines = []
    for p in root.iter(f"{_W}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append(" ")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        lines.append("".join(parts))
    return "\n".join(lines)


def _cues(text: str) -> str:
    """.vtt / .srt: drop the header, cue numbers and timings; <v Name> becomes "Name: "."""
    out, skip_block = [], False
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            skip_block = False
            continue
        if skip_block or stripped == "WEBVTT" or stripped.startswith(("WEBVTT ", "Kind:", "Language:")):
            continue
        if stripped.startswith(("NOTE", "STYLE", "REGION")):
            skip_block = True
            continue
        if _TIME.match(stripped) or stripped.isdigit():
            continue
        voice = _VOICE.search(stripped)
        if voice:
            stripped = f"{voice.group(1).strip()}: {_TAG.sub('', voice.group(2)).strip()}"
        else:
            stripped = _TAG.sub("", stripped).strip()
        if stripped:
            out.append(stripped)
    return "\n".join(out)


def _headers(text: str) -> str:
    """Zoom / Teams exports put the speaker and time on a line of their own: fold them into "Name: words"."""
    out, speaker = [], None
    for line in text.split("\n"):
        h = _HEADER.match(line)
        if h:
            speaker = h.group(1).strip()
            continue
        if line.strip():
            out.append(f"{speaker}: {line.strip()}" if speaker and not _LABEL.match(line) else line.strip())
    return "\n".join(out)


def _merge(text: str) -> str:
    """Consecutive lines by the same speaker become one turn (subtitle files cut sentences into pieces)."""
    out: list[str] = []
    last = None
    for line in text.split("\n"):
        m = _LABEL.match(line)
        who = m.group(1) if m else None
        if who and who == last and out:
            out[-1] += " " + line[len(who) + 1:].strip()
        else:
            out.append(line)
        last = who
    return "\n".join(out)


def to_text(data: bytes, filename: str | None) -> str:
    """The transcript as plain text. Raises TranscriptError for anything that is not a transcript we can read."""
    name = (filename or "").lower()
    if name.endswith(".docx"):
        text = _docx_text(data)
    else:
        if b"\x00" in data[:8192]:
            raise TranscriptError("Send a .txt, .vtt, .srt or .docx transcript, or paste the text")
        text = data.decode("utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if name.endswith((".vtt", ".srt")) or text.lstrip().startswith("WEBVTT") or "-->" in text[:3000]:
        text = _cues(text)
    text = _headers(text)
    text = _merge(text).strip()
    if len(text) < 40:
        raise TranscriptError("The transcript is empty or too short to read")
    return text[:MAX_CHARS]


@dataclass
class Turn:
    speaker: str | None
    start: int
    end: int


def turns(text: str) -> list[Turn]:
    """Each line with who said it (None when the line has no label)."""
    out, pos = [], 0
    for line in text.split("\n"):
        m = _LABEL.match(line)
        out.append(Turn(m.group(1).strip() if m else None, pos, pos + len(line)))
        pos += len(line) + 1
    return out


def speakers(text: str) -> list[str]:
    seen: list[str] = []
    for t in turns(text):
        if t.speaker and t.speaker not in seen:
            seen.append(t.speaker)
    return seen
