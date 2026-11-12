"""Bounded JSON projection for reports. No whole-document object is constructed."""
from __future__ import annotations

import json
from typing import TextIO


def _invalid_constant(value: str):
    raise ValueError(f'Non-JSON numeric constant: {value}')


class JsonStream:
    """Yield (path, value) for paths such as ('runs', '*', 'results', '*').

    Selected records and individual strings have a hard character budget. JSON
    nesting is capped. Unselected arrays are walked without retaining their items.
    This is a narrow report reader, not an incremental network JSON protocol.
    """
    def __init__(self, source: TextIO, paths, *, chunk_size=65536, max_item=8*1024*1024):
        self.source = source
        self.paths = [tuple(p) for p in paths]
        self.chunk_size, self.max_item = chunk_size, max_item
        self.buffer = ''
        self.pos = 0
        self.eof = False
        self.peak_buffer = 0
        self.containers = set()
        self.decoder = json.JSONDecoder(parse_constant=_invalid_constant)

    def _fill(self):
        self.buffer = self.buffer[self.pos:]
        self.pos = 0
        chunk = self.source.read(self.chunk_size)
        self.eof = not chunk
        self.buffer += chunk
        self.peak_buffer = max(self.peak_buffer, len(self.buffer))

    def _peek(self):
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos] in ' \r\n\t':
                self.pos += 1
            if self.pos < len(self.buffer):
                return self.buffer[self.pos]
            if self.eof:
                return ''
            self._fill()

    def _expect(self, expected):
        if self._peek() != expected:
            raise ValueError(f'Malformed JSON: expected {expected!r}')
        self.pos += 1

    def _value(self):
        if not self._peek():
            raise ValueError('Unexpected end of JSON')
        self.buffer = self.buffer[self.pos:]
        self.pos = 0
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer)
                if end > self.max_item:
                    raise ValueError('JSON record exceeds item budget')
                # A number may continue in the next chunk. Never accept its prefix.
                if end == len(self.buffer) and not self.eof:
                    if len(self.buffer) > self.max_item:
                        raise ValueError('JSON record exceeds item budget')
                    self._fill()
                    continue
                if end < len(self.buffer) and self.buffer[end] not in ' \r\n\t,]}':
                    raise ValueError('Malformed JSON value delimiter')
                self.pos = end
                return value
            except json.JSONDecodeError as exc:
                if self.eof:
                    raise ValueError('Malformed or incomplete JSON') from exc
                if len(self.buffer) > self.max_item:
                    raise ValueError('JSON record exceeds item budget') from exc
                self._fill()

    def _walk(self, path=(), depth=0):
        if depth > 64:
            raise ValueError('JSON nesting exceeds 64 levels')
        normalized = tuple('*' if isinstance(p, int) else p for p in path)
        if any(len(p)==len(normalized) and all(a=='*' or a==b for a,b in zip(p,normalized)) for p in self.paths):
            yield path, self._value()
            return
        char = self._peek()
        if char in ('{', '['):
            if any(len(p)>=len(normalized) and all(a=='*' or a==b for a,b in zip(p,normalized)) for p in self.paths):
                self.containers.add(normalized)
        if char == '{':
            self.pos += 1
            if self._peek() == '}':
                self.pos += 1
                return
            while True:
                # Object keys need ':' as a legal following delimiter.
                if self._peek() != '"':
                    raise ValueError('JSON object key must be a string')
                key = self._key()
                self._expect(':')
                yield from self._walk((*path, key), depth+1)
                if self._peek() == '}':
                    self.pos += 1
                    break
                self._expect(',')
        elif char == '[':
            self.pos += 1
            if self._peek() == ']':
                self.pos += 1
                return
            index = 0
            while True:
                yield from self._walk((*path, index), depth+1)
                index += 1
                if self._peek() == ']':
                    self.pos += 1
                    break
                self._expect(',')
        elif char:
            self._value()
        else:
            raise ValueError('Unexpected end of JSON')

    def _key(self):
        self.buffer = self.buffer[self.pos:]
        self.pos = 0
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer)
                if not isinstance(value, str) or len(value)>4096:
                    raise ValueError('JSON object key exceeds budget')
                self.pos = end
                return value
            except json.JSONDecodeError as exc:
                if self.eof or len(self.buffer)>16384:
                    raise ValueError('Invalid or oversized JSON object key') from exc
                self._fill()

    def __iter__(self):
        yield from self._walk()
        if self._peek():
            raise ValueError('Trailing data after JSON document')


def json_lines(source: TextIO, max_item=8*1024*1024):
    while line := source.readline(max_item+1):
        if len(line)>max_item:
            raise ValueError('JSONL record exceeds budget')
        if line.strip():
            yield json.loads(line, parse_constant=_invalid_constant)
