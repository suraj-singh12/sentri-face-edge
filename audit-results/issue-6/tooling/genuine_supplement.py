"""Run only existing, locally authorized QA-J01; keep all captures private.
No downloads, altered model declarations, UI patches or new inference fixtures.
"""
import sys,json,hashlib,argparse
from pathlib import Path
from types import SimpleNamespace
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'scripts'))
import qa_foundation as qa
import qa_browser as ui
from datetime import datetime
out=ROOT/('qa-fixtures/runs/issue-6-audit/genuine-'+datetime.now().strftime('%Y%m%d-%H%M%S'));out.mkdir(exist_ok=False)
report={'source_sha':'b457f0a723e845dd1a92a07a577072c85146c89a','source_product_files_modified':False}
steps=[];original=ui.action;original_snapshot=ui.snapshot;last_page=None

def capture_action(page,endpoint,invoke):
    global last_page
    last_page=page
    result=original(page,endpoint,invoke)
    name=f'{len(steps)+1:02d}-{endpoint.split("/")[-1]}-response.png'
    page.screenshot(path=str(out/name),full_page=False)
    steps.append({'endpoint':endpoint,'file':name,'sha256':hashlib.sha256((out/name).read_bytes()).hexdigest(),'qualification':'Actual action response; may show transient state; private genuine-photo evidence'})
    (out/'steps.json').write_text(json.dumps(steps,indent=2))
    return result
ui.action=capture_action

def stable_snapshot(context,*args,**kwargs):
    result=original_snapshot(context,*args,**kwargs)
    last_page.get_by_role('tab',name='People',exact=True).wait_for()
    last_page.get_by_role('tablist').first.get_by_role('tab',name='People',exact=True).click()
    back=last_page.get_by_role('button',name='Back to people',exact=True)
    if back.count(): back.click()
    last_page.get_by_role('button',name='Open '+result['actor'],exact=True).click()
    last_page.get_by_role('button',name='Manage Recognition References',exact=True).wait_for()
    name=f"stable-{len(steps)+1:02d}-verified-profile.png"
    last_page.screenshot(path=str(out/name),full_page=False)
    steps.append({'file':name,'sha256':hashlib.sha256((out/name).read_bytes()).hexdigest(),'qualification':'Stable actual profile reached via UI after independent backend snapshot; private genuine-photo evidence'})
    (out/'steps.json').write_text(json.dumps(steps,indent=2))
    last_page.get_by_role('button',name='Back to people',exact=True).click()
    return result
ui.snapshot=stable_snapshot
try:
    cli=argparse.ArgumentParser();cli.add_argument('--actor',required=True);fixture_actor=cli.parse_args().actor
    args=SimpleNamespace(actor=fixture_actor,date='2026-11-09',location='Private QA occurrence',fixtures=ROOT/'qa-fixtures/marvel-actors',chromium=None,headed=False)
    config=qa.model_inputs(ROOT/'qa-fixtures/models.json')
    pair=qa.verified_pair(args.fixtures,args.actor)
    report['model_hashes']={k:config[k+'_sha256'] for k in ('detector','recognizer')}
    qa.execute(args,config,pair,out,report)
    report['result']='PASS'
except Exception as exc:
    report.update(result='BLOCKED' if isinstance(exc,(ui.Blocked,FileNotFoundError,ValueError)) else 'FAIL',error=str(exc))
finally:
    (out/'private-report.json').write_text(json.dumps(report,indent=2,default=str))
    print(json.dumps({'result':report.get('result'),'inference_executed':report.get('inference_executed',False),'restart_verified':report.get('restart_verified',False),'cleanup_completed':report.get('cleanup_completed',False),'captures':len(steps)}))
