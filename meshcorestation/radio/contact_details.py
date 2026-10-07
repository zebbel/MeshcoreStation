"""Join device contact metadata with the locally recorded history, by full key."""
from meshcorestation.config import TIMEZONE


def details(contact, database):
    result = {'device': dict(contact), 'timezone': TIMEZONE.key, 'repeater': None, 'position': None, 'battery': None}
    key = str(contact.get('public_key', '')).lower()
    # Historical information is labeled separately from the device's current contact.
    for table, label in (('repeaters', 'repeater'), ('companion_positions', 'position')):
        row = database.db.execute(f'SELECT * FROM {table} WHERE lower(public_key)=?', (key,)).fetchone()
        result[label] = dict(row) if row else None
    row = database.db.execute('SELECT * FROM voltage_samples WHERE public_key=? ORDER BY sampled_at DESC,id DESC LIMIT 1', (key,)).fetchone()
    result['battery'] = dict(row) if row else None
    row = database.db.execute('SELECT COUNT(*) AS commands, MAX(recv_time) AS last_command FROM logger WHERE lower(sender_public_key)=?', (key,)).fetchone()
    result['command_history'] = dict(row)
    return result
