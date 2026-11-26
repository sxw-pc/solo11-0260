"""Publish and apply ordered rules for local audit follow-up routing."""
import json

from .store import act, one

FIELDS = ('site', 'severity', 'signal')
DESTINATIONS = frozenset(('pager', 'manual', 'desk'))


def select(rules, dimensions):
    for rule in rules:
        if all(rule[field] == '*' or rule[field] == dimensions[field] for field in FIELDS):
            return rule['destination']
    return 'desk'


def active(db, scope):
    record = one(db, 'SELECT * FROM routing_versions WHERE scope=? ORDER BY version DESC LIMIT 1', (scope,))
    if record:
        record['rules'] = json.loads(record['rules'])
    return record


def handle(db, command):
    if command['op'] != 'publish':
        return {'decision': 'unknown_operation'}
    scope, version, rules = command['scope'], command['version'], command['rules']
    old = active(db, scope)
    if type(version) is not int or version != (old['version'] + 1 if old else 1):
        return {'decision': 'routing_version_denied'}
    if not isinstance(rules, list) or any(
            not isinstance(rule, dict) or set(rule) != set(FIELDS) | {'destination'}
            or any(not isinstance(rule[k], str) or not rule[k] for k in (*FIELDS, 'destination'))
            or rule['destination'] not in DESTINATIONS for rule in rules):
        return {'decision': 'routing_rule_denied'}
    db.execute('INSERT INTO routing_versions VALUES(?,?,?)', (scope, version, json.dumps(rules, sort_keys=True)))
    return {'decision': 'routing_published', 'version': version}


def run(db, command):
    return act(db, 'routing', command, handle)
