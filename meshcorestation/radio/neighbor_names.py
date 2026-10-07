"""Resolve radio neighbor prefixes against locally recorded repeater identities."""
import re


def with_neighbor_names(db, data):
    neighbors = []
    for item in data.get('neighbours', []):
        row = dict(item)
        prefix = str(row.get('pubkey', '')).lower()
        row.pop('name', None)
        # An ambiguous prefix must never be presented as a known identity.
        if re.fullmatch(r'[0-9a-f]{2,64}', prefix) and len(prefix) % 2 == 0:
            matches = db.execute('SELECT name FROM repeaters WHERE lower(public_key) LIKE ? LIMIT 2', (prefix + '%',)).fetchall()
            if len(matches) == 1 and isinstance(matches[0][0], str) and matches[0][0].strip():
                row['name'] = matches[0][0].strip()
        neighbors.append(row)
    return {**data, 'neighbours': neighbors}
