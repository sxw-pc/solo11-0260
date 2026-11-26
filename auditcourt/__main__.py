import argparse,json
from pathlib import Path
from .store import connect,replay,many
from . import capture,seal,hold,custody,coverage,feed,followup,controls,maintenance,routing,triage
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['capture','seal','hold','custody','coverage','feed','followup','controls','maintenance','routing','triage','demo','replay','report']);p.add_argument('--db',default='demo.sqlite');p.add_argument('--fixture');a=p.parse_args()
    if a.command=='replay':result=replay(a.db)
    else:
        db=connect(a.db)
        if a.command=='report':result=many(db,'SELECT * FROM events ORDER BY seq')
        else:
            paths=([Path('fixtures')/n for n in ['capture_normal.json','seal_normal.json','hold_normal.json','capture_failure.json','seal_failure.json','hold_failure.json']] if a.command=='demo' else [Path(a.fixture)] if a.fixture else [])
            if not paths:p.error('--fixture required')
            modules={'capture':capture,'seal':seal,'hold':hold,'custody':custody,'coverage':coverage,'feed':feed,'followup':followup,'controls':controls,'maintenance':maintenance,'routing':routing,'triage':triage};result=[]
            for path in paths:
                default=path.name.split('_')[0] if a.command=='demo' else a.command
                result.append({'fixture':str(path),'outcomes':[modules[x.get('subsystem',default)].run(db,x) for x in json.loads(path.read_text(encoding='utf8'))]})
        db.close()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if a.command=='replay' and not result['verified']:raise SystemExit(2)
if __name__=='__main__':main()
