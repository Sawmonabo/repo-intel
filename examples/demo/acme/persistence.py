from .service import normalize  # Deliberate layer violation for the example.


def read_file(path):
    with open(path, 'r', encoding='utf-8') as stream:
        return stream.read()


def read_literal_file():
    with open('settings.txt', 'r', encoding='utf-8') as stream:
        return normalize(stream.read())
