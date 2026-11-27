"""Read and update the .ANIMATION file of a Torchlight 2 model.

The file is a text file in UTF-16 little endian with a byte order mark.
It has one [ANIMATION] entry for each animation.
People edit this file by hand, so this module only adds entries.
It never changes or deletes an existing entry.
"""
import os
import re
import shutil

BOM = b'\xff\xfe'
START_TAG = '[ANIMATIONS]'
END_TAG = '[/ANIMATIONS]'

_ENTRY = re.compile(r'\[ANIMATION\](.*?)\[/ANIMATION\]', re.S)
_FILE = re.compile(r'<STRING>FILE:([^\r\n]*)')
_NAME = re.compile(r'<STRING>NAME:([^\r\n]*)')


def read_entries(text):
    """Return a list of (file, name) for the entries in the text."""
    entries = []
    for match in _ENTRY.finditer(text):
        # The events ([KEY]) have a NAME field too. Read only the part before them.
        head = match.group(1).split('[KEY]')[0]
        file_match = _FILE.search(head)
        name_match = _NAME.search(head)
        entries.append((file_match.group(1).strip() if file_match else '',
                        name_match.group(1).strip() if name_match else ''))
    return entries


def format_duration(duration):
    return '%.6g' % duration


def build_entry(file_name, name, duration, eol='\r\n'):
    lines = ['\t[ANIMATION]',
             '\t\t<STRING>FILE:%s' % file_name,
             '\t\t<STRING>NAME:%s' % name,
             '\t\t<FLOAT>DURATION:%s' % format_duration(duration),
             '\t[/ANIMATION]']
    return eol.join(lines) + eol


def get_backup_path(path):
    """Return a backup path that does not exist yet."""
    backup = path + '.bak'
    number = 1
    while os.path.exists(backup):
        backup = '%s.bak%d' % (path, number)
        number += 1
    return backup


def update_animation_file(path, animations):
    """Add an entry for each animation that has none. Return (added, skipped).

    animations is a list of (file name, animation name, duration in seconds).
    An animation has an entry when the file name or the name matches an
    entry. The match ignores case. Raise ValueError when the file has a
    format that this function does not know. Then the file does not change.
    """
    eol = '\r\n'
    text = None
    existing = []
    if os.path.isfile(path):
        with open(path, 'rb') as f:
            raw = f.read()
        if raw[:2] != BOM:
            raise ValueError("The file is not UTF-16 little endian with a byte order mark.")
        try:
            text = raw[2:].decode('utf-16-le')
        except UnicodeDecodeError:
            raise ValueError("The file is not valid UTF-16.")
        end = text.rfind(END_TAG)
        if end < 0:
            raise ValueError("The file has no %s line." % END_TAG)
        if '\r\n' not in text and '\n' in text:
            eol = '\n'
        existing = read_entries(text)

    have_files = {file_name.lower() for file_name, _ in existing}
    have_names = {name.lower() for _, name in existing}
    added = []
    skipped = []
    new_text = ''
    for file_name, name, duration in animations:
        if file_name.lower() in have_files or name.lower() in have_names:
            skipped.append(name)
            continue
        new_text += build_entry(file_name, name, duration, eol)
        have_files.add(file_name.lower())
        have_names.add(name.lower())
        added.append(name)
    if not added:
        return added, skipped

    if text is None:
        result = START_TAG + eol + new_text + END_TAG + eol
    else:
        before = text[:end]
        if before and not before.endswith('\n'):
            before += eol
        result = before + new_text + text[end:]
        shutil.copy2(path, get_backup_path(path))

    with open(path, 'wb') as f:
        f.write(BOM + result.encode('utf-16-le'))
    return added, skipped
