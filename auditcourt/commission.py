"""Run a conditional commissioning instruction on two synthetic control objects."""
from . import controls
from .store import act, one


def handle(db, command):
    op, name = command['op'], command['id']
    if op != 'execute':
        return {'decision': 'unknown_operation'}
    source = one(db, 'SELECT * FROM control_objects WHERE id=?', (command['input'],))
    target = one(db, 'SELECT * FROM control_objects WHERE id=?', (command['target'],))
    if not source or not target or source['id'] == target['id']:
        return {'decision': 'commission_object_denied'}
    if any(type(command[key]) is not int for key in ('threshold', 'on_low', 'on_high')):
        return {'decision': 'commission_instruction_denied'}
    branch = 'high' if source['value'] >= command['threshold'] else 'low'
    selected = command['on_high'] if branch == 'high' else command['on_low']
    result = controls.handle(db, {
        'op': 'apply', 'id': name, 'object': target['id'],
        'permit': command['permit'], 'operator': command['operator'], 'at': command['at'],
        'revision': target['revision'], 'delta': selected - target['value'],
    })
    if result['decision'] != 'control_changed':
        return result
    db.execute('INSERT INTO commission_runs VALUES(?,?,?,?,?,?,?,?,?)', (
        name, source['id'], source['revision'], source['value'], target['id'],
        command['threshold'], command['on_low'], command['on_high'], branch,
    ))
    return {'decision': 'commission_applied', 'branch': branch, 'value': result['value'], 'input_revision': source['revision']}


def run(db, command):
    return act(db, 'commission', command, handle)
