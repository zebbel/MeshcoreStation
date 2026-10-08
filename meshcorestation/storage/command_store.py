"""Transactional command registry. Defaults are seeded once, never resurrected."""
import hashlib
import json
import re
from meshcorestation.commands.templates import fields, command_list, MAX_COMMANDS, MAX_REPLY_BYTES

DEFAULTS = [
    dict(id='help', trigger='?', help='Show available commands', reply='{command_list}', action='reply'),
    dict(id='status', trigger='status', help='Show repeater count', reply='@{sender_name} | {repeater_count} repeaters.', action='reply'),
    dict(id='ping', trigger='ping', help='Test the connection', reply='@{sender_name} | {hop_count} hops | SNR {snr} | RSSI {rssi} dBm | direct {direct_distance}km | route {route_distance}km | scope {scope_name}.', action='reply'),
]
LEGACY = [
    dict(id='position', trigger='position', help='Update saved coordinates', reply='@[{sender_name}] {result}', action='position'),
    dict(id='scope', trigger='scope', help='Add a reply scope', reply='@[{sender_name}] {result}', action='scope'),
]


def initialize(db, legacy=False):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bot_commands'").fetchone()
    db.execute('CREATE TABLE IF NOT EXISTS bot_commands (id TEXT PRIMARY KEY, trigger TEXT NOT NULL UNIQUE, help TEXT NOT NULL, reply TEXT NOT NULL, action TEXT NOT NULL, sort_order INTEGER NOT NULL)')
    columns = {row[1] for row in db.execute('PRAGMA table_info(bot_commands)')}
    if 'failure_reply' not in columns:
        db.execute("ALTER TABLE bot_commands ADD COLUMN failure_reply TEXT NOT NULL DEFAULT '@{sender_name} | {result}'")
    if not exists:
        for index, item in enumerate(DEFAULTS + (LEGACY if legacy else [])):
            db.execute('INSERT INTO bot_commands (id,trigger,help,reply,action,sort_order) VALUES (?,?,?,?,?,?)', (item['id'], item['trigger'], item['help'], item['reply'], item['action'], index))

    db.execute("UPDATE bot_commands SET reply=replace(reply,'@{sender_name}','@[{sender_name}]'), failure_reply=replace(failure_reply,'@{sender_name}','@[{sender_name}]') WHERE action='position'")


def read(db):
    rows = db.execute('SELECT id,trigger,help,reply,action,failure_reply FROM bot_commands ORDER BY sort_order').fetchall()
    result = [dict(zip(('id', 'trigger', 'help', 'reply', 'action', 'failure_reply'), row)) for row in rows]
    # Protect the mandatory help command even if the database was edited manually.
    if not any(item['id'] == 'help' and item['trigger'] == '?' for item in result):
        result = [dict(DEFAULTS[0])] + [item for item in result if item['trigger'] != '?' and item['id'] != 'help']
    return result


def snapshot(db):
    commands = read(db)
    revision = hashlib.sha256(json.dumps(commands, sort_keys=True).encode()).hexdigest()
    return {'ok': True, 'commands': commands, 'revision': revision}


def validate(items, before):
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_COMMANDS:
        raise ValueError(f'Keep between 1 and {MAX_COMMANDS} commands, including ?. ')
    existing = {item['id']: item for item in before}
    result, ids, triggers = [], set(), set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError('Invalid command.')
        identity, trigger, help_text, reply = (raw.get(k) for k in ('id', 'trigger', 'help', 'reply'))
        if not isinstance(identity, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', identity) or identity in ids:
            raise ValueError('Invalid or duplicate command identifier.')
        if not isinstance(trigger, str):
            raise ValueError('Enter a command name.')
        trigger = trigger.strip().casefold()
        if not re.fullmatch(r'\?|[a-z0-9][a-z0-9_-]{0,29}', trigger) or trigger in triggers:
            raise ValueError('Use a unique command of 1–30 letters, digits, hyphens or underscores.')
        if (identity == 'help') != (trigger == '?'):
            raise ValueError('? cannot be renamed or replaced.')
        if not isinstance(help_text, str) or not help_text.strip() or len(help_text.encode()) > 100 or re.search(r'[\x00-\x1f\x7f]', help_text):
            raise ValueError('Help text must contain 1–100 UTF-8 bytes on one line.')
        placeholders = fields(reply)
        action = raw.get('action', existing.get(identity, {}).get('action', 'reply'))
        if action not in ('reply', 'position', 'scope'):
            raise ValueError('Choose Reply, Update sender position or Add scope.')
        if trigger == '?' and action != 'reply':
            raise ValueError('? must use the Reply action.')
        failure_reply = raw.get('failure_reply', '@{sender_name} | {result}')
        if action == 'position':
            reply = reply.replace('@{sender_name}', '@[{sender_name}]')
            if isinstance(failure_reply, str):
                failure_reply = failure_reply.replace('@{sender_name}', '@[{sender_name}]')
        if action != 'reply':
            placeholders |= fields(failure_reply)
        if placeholders & {'result', 'latitude', 'longitude', 'altitude', 'added_scope'} and action == 'reply':
            raise ValueError('Action result placeholders require an action.')
        if trigger == '?' and 'command_list' not in placeholders:
            raise ValueError('The ? reply must include {command_list}.')
        result.append(dict(id=identity, trigger=trigger, help=help_text.strip(), reply=reply, action=action, failure_reply=failure_reply if action != 'reply' else '@{sender_name} | {result}'))
        ids.add(identity); triggers.add(trigger)
    if 'help' not in ids:
        raise ValueError('? cannot be deleted.')
    if len(command_list(result).encode()) > MAX_REPLY_BYTES - 512:
        raise ValueError('The combined help text is too long.')
    return sorted(result, key=lambda item: item['id'] != 'help')


def replace(db, items, expected):
    db.execute('BEGIN IMMEDIATE')
    before = snapshot(db)
    if before['revision'] != expected:
        raise RuntimeError('Commands changed in another window. Reload before saving.')
    commands = validate(items, before['commands'])
    db.execute('DELETE FROM bot_commands')
    for i, item in enumerate(commands):
        db.execute('INSERT INTO bot_commands (id,trigger,help,reply,action,sort_order,failure_reply) VALUES (?,?,?,?,?,?,?)', (item['id'], item['trigger'], item['help'], item['reply'], item['action'], i, item['failure_reply']))
    return snapshot(db)
