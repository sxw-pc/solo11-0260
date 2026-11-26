from .store import act,one
def handle(db,x):
    op=x['op']
    if op=='policy':
        old=one(db,'SELECT * FROM retention_policies WHERE object_uid=?',(x['object_uid'],))
        if old and x['generation']<=old['generation']:return {'decision':'stale_policy'}
        if x['expires']<=x['at']:return {'decision':'invalid_retention'}
        db.execute('INSERT INTO retention_policies VALUES(?,?,?,?,?) ON CONFLICT(object_uid) DO UPDATE SET id=excluded.id,expires=excluded.expires,generation=excluded.generation,state=excluded.state',(x['id'],x['object_uid'],x['expires'],x['generation'],'active'))
        return {'decision':'retention_active'}
    if op=='hold':
        c=one(db,'SELECT * FROM evidence_chains WHERE id=?',(x['chain'],))
        if not c or c['object_uid']!=x['object_uid'] or c['sealed_at']>x['at'] or x['expires']<=x['at'] or not x.get('actor'):
            return {'decision':'hold_denied'}
        db.execute('INSERT INTO legal_holds VALUES(?,?,?,?,?,?)',(x['id'],x['object_uid'],x['chain'],x['actor'],x['expires'],'active'))
        return {'decision':'hold_active'}
    if op=='release':
        h=one(db,'SELECT * FROM legal_holds WHERE id=?',(x['id'],))
        if not h or h['state']!='active' or h['actor']!=x['actor']:
            return {'decision':'release_denied'}
        db.execute("UPDATE legal_holds SET state='released' WHERE id=?",(x['id'],))
        return {'decision':'released'}
    if op=='disclose':
        c=one(db,'SELECT * FROM evidence_chains WHERE id=?',(x['chain'],))
        h=one(db,"SELECT * FROM legal_holds WHERE object_uid=? AND chain_id=? AND actor=? AND state='active' AND expires>? ORDER BY id LIMIT 1",(x['object_uid'],x['chain'],x['requester'],x['at']))
        if not c or c['object_uid']!=x['object_uid'] or c['sealed_at']>x['at'] or not h or x['scope'] not in ('summary','full'):
            return {'decision':'disclosure_denied'}
        if x['scope']=='full' and c['rating']!='complete':return {'decision':'chain_not_complete'}
        db.execute('INSERT INTO disclosure_cases VALUES(?,?,?,?,?,?,?)',(x['id'],x['object_uid'],c['id'],x['requester'],x['scope'],'disclosed',x['at']))
        count=one(db,'SELECT COUNT(*) n FROM chain_members WHERE chain_id=?',(c['id'],))['n']
        return {'decision':'disclosed','chain_version':c['version'],'members':count}
    if op=='cleanup':
        p=one(db,'SELECT * FROM retention_policies WHERE object_uid=?',(x['object_uid'],))
        if not p:return {'decision':'no_retention_policy'}
        hold=one(db,"SELECT 1 FROM legal_holds WHERE object_uid=? AND state='active' AND expires>?",(x['object_uid'],x['at']))
        conflicts=one(db,"SELECT COUNT(*) n FROM conflict_cases c JOIN audit_events e ON e.source=c.source AND e.source_generation=c.source_generation AND e.seq=c.seq WHERE e.object_uid=? AND c.state='open'",(x['object_uid'],))['n']
        reason='retention_not_expired' if p['expires']>x['at'] else 'legal_hold' if hold else 'source_conflict' if conflicts else 'eligible'
        decision='retain' if reason!='eligible' else 'cleanup_approved'
        db.execute('INSERT INTO cleanup_cases VALUES(?,?,?,?,?)',(x['id'],x['object_uid'],decision,x['at'],reason))
        return {'decision':decision,'reason':reason}
    return {'decision':'unknown_operation'}
def run(db,x):return act(db,'hold',x,handle)
