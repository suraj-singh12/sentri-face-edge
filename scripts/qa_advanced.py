"""Bounded Advanced scenarios. Truth is authored before writes; no history reducer.

Reuse Moderate's completed reviews, projection adapter/comparator and immutable
history audit. Only observed reads call canonical/graph production algorithms.
"""
from copy import deepcopy
from unittest.mock import patch
import uuid

import qa_foundation as qa
import qa_moderate as m


def serial_truth(truth):
    result=deepcopy(truth)
    if 'edges' in result:
        result['edges']=[dict(pair=list(pair),counts=counts) for pair,counts in sorted(result['edges'].items())]
    return result


def event(ids, location, media=1):
    return dict(participant_ids=sorted(ids), location=location, media_count=media)


def audit(s, include_journal=False):
    """Exact domain rows for rollback/rebuild invariance, not effective truth."""
    from tests.test_graph_projection_rebuild import GraphProjectionRebuildTest
    tables=GraphProjectionRebuildTest.AUTHORITATIVE_TABLES + (
        'encounter_metadata_revisions','encounter_participant_revisions','encounter_relation_decisions')
    if include_journal:
        tables += ('operation_journal','operation_journal_status_history')
    with s._connect() as conn:
        return {t: sorted([tuple(r) for r in conn.execute('SELECT * FROM ' + t)], key=repr)
                for t in tables}


def verify(s, people, events, edges, canonical, raw, date, read=None):
    observed = m.snapshot(read or m.store_reader(s), people, events, edges, date)
    for pid, survivor in canonical.items():
        qa.assert_expected(survivor, s.resolve_canonical_person_id(pid), 'Advanced.canonical')
        qa.assert_expected(survivor, s.get_effective_person(pid).person_id, 'Advanced.People')
    for oid, original in raw.items():
        qa.assert_expected(original, m.history(s, oid), 'Advanced.provenance')
    qa.assert_expected(True, s.validate_graph_projection()['valid'], 'Advanced.graph_integrity')
    from sentriface.integrity import ReadOnlyIntegrityChecker
    integrity=ReadOnlyIntegrityChecker(s.db_path,database_key=s.database_key).run()
    qa.assert_expected('PASS',integrity.status,'Advanced.P11.integrity')
    return observed


def h01(s, date, proofs, visit=None):
    a, b, c = [s.create_person(n) for n in ('Advanced A', 'Advanced B', 'Advanced C')]
    a, b, c = a.person_id, b.person_id, c.person_id
    # Expected identities, media cardinality and locations predate finalization.
    specifications = [([a], 'X', 1), ([b], 'Y', 1), ([a,c], 'Z', 2)]
    events = {}
    for i, (ids, loc, media) in enumerate(specifications):
        expectation = event(ids, loc, media)
        oid = m.finalize(s, 'h01-' + str(i), [s.get_person(p) for p in ids], date, loc)
        events[oid] = expectation
    x, y, z = events
    people = [a,b,c]
    canonical = {a:a,b:b,c:c}
    edges = {tuple(sorted([a,c])): {'CO_OBSERVED':1}}
    raw = {oid:m.history(s, oid) for oid in events}
    for oid,(ids,loc,media) in zip(events,specifications):
        qa.assert_expected(sorted(ids),sorted(r['person_id'] for r in raw[oid]['original_review_decisions']),'Advanced.original.accepted_decisions')
        qa.assert_expected(sorted(ids),sorted(r['original_person_id'] for r in raw[oid]['observation_face_assignments']),'Advanced.original.face_assignments')
        qa.assert_expected(media,len(raw[oid]['observation_media']),'Advanced.original.media')
    operations = []
    expected_sources = {'h01-2-metadata': dict(kind='CO_OBSERVED',source=z,raw=sorted([a,c]))}
    def check(action):
        truth = dict(people=people, events=deepcopy(events), edges=deepcopy(edges), canonical=deepcopy(canonical))
        actual = verify(s, people, events, edges, canonical, raw, date)
        source_rows=[]
        for row in actual['evidence_proof']:
            source_rows.append((row['provenance']['created_operation_id'],row['evidence_type'],
                row['supporting_references'][0]['source_entity_id'],sorted(row['raw_endpoints'])))
        qa.assert_expected(sorted((op,v['kind'],v['source'],v['raw']) for op,v in expected_sources.items()),
            sorted(source_rows),'Advanced.evidence.exact_sources')
        for op in operations:
            qa.assert_expected('COMMITTED', s.get_operation(op)['status'], 'Advanced.journal')
        m.record(proofs, action, serial_truth(truth), actual)
        proofs[-1].update(provenance=deepcopy(raw), expected_sources=deepcopy(expected_sources),
            operations=[s.get_operation(op) for op in operations], differences=[],
            stored_state={table:rows for table,rows in audit(s).items() if table in (
                'persons','observations','observation_participants','identity_corrections',
                'relationship_evidence','merge_operations','notes','note_mentions',
                'encounter_metadata_revisions','encounter_participant_revisions','encounter_relation_decisions')})
        if visit: visit(s, truth, raw, action)
    check('Initial accepted A at X, B at Y, independent A/C at Z')
    events[x] = event([b], 'X')
    op = str(uuid.uuid4()); operations.append(op)
    m.correction(s, x, op, participant_correction=dict(action='REASSIGN', person_id=a, to_person_id=b))
    check('Correct only X participant A -> B; independent A/C unchanged')
    events[x]['location'] = 'X revised'
    op = str(uuid.uuid4()); operations.append(op)
    m.correction(s, x, op, event_details=dict(place_seen='X revised'))
    check('Second correction: X location only')
    edges[tuple(sorted([a,c]))]['MANUAL_ASSOCIATION'] = 1
    op = str(uuid.uuid4()); operations.append(op)
    expected_sources[op]=dict(kind='MANUAL_ASSOCIATION',source=op,raw=sorted([a,c]))
    manual = s.create_manual_association(a, c, op)
    check('Independent A/C manual assertion')
    # Duplicate canonical manual pair will collapse, preserving both raw rows.
    edges[tuple(sorted([b,c]))] = {'MANUAL_ASSOCIATION':1}
    op = str(uuid.uuid4()); operations.append(op)
    redundant_op=op
    expected_sources[op]=dict(kind='MANUAL_ASSOCIATION',source=op,raw=sorted([b,c]))
    s.create_manual_association(b, c, op)
    check('Independent B/C standing assertion before merge')
    people = [b,c]; canonical[a] = b
    events[z] = event([b,c], 'Z', 2)
    edges = {tuple(sorted([b,c])): {'CO_OBSERVED':1, 'MANUAL_ASSOCIATION':1}}
    op = str(uuid.uuid4()); operations.append(op)
    with s._connect() as conn:
        raw_manual_before=[dict(r) for r in conn.execute("SELECT * FROM relationship_evidence WHERE evidence_type = 'MANUAL_ASSOCIATION' ORDER BY evidence_id")]
    del expected_sources[redundant_op]
    result = s.execute_identity_merge(a, b, op)
    qa.assert_expected(b, result['canonical_person_id'], 'Advanced.merge.survivor')
    with s._connect() as conn:
        raw_manual_after=[dict(r) for r in conn.execute("SELECT * FROM relationship_evidence WHERE evidence_type = 'MANUAL_ASSOCIATION' ORDER BY evidence_id")]
    immutable=lambda rows:[{k:v for k,v in row.items() if k not in ('active','deactivated_operation_id','deactivated_at')} for row in rows]
    qa.assert_expected(immutable(raw_manual_before),immutable(raw_manual_after),'Advanced.manual.raw_provenance')
    qa.assert_expected(1,sum(r['active'] for r in raw_manual_after),'Advanced.manual.canonical_unique')
    manifest = s.get_merge_operation(op)
    qa.assert_expected(a, manifest.source_person_id, 'Advanced.merge.source')
    qa.assert_expected(b, manifest.target_person_id, 'Advanced.merge.target')
    before_retry = audit(s)
    qa.assert_expected(result, s.execute_identity_merge(a,b,op), 'Advanced.merge.retry')
    qa.assert_expected(before_retry, audit(s), 'Advanced.merge.retry_no_writes')
    check('Canonical A -> B; collapse redundant standing pair, preserve raw history')
    edges[tuple(sorted([b,c]))]['NOTE_REFERENCE'] = 1
    op = str(uuid.uuid4()); operations.append(op)
    s.update_person_notes(b, 'Selected @C; literal @A', '', 'QA', op, [c])
    # Note evidence references the immutable selected-mention occurrence, not
    # the mutable Note container. Its generated ID is only a handle.
    with s._connect() as conn:
        mentions=[dict(r) for r in conn.execute('SELECT * FROM note_mentions WHERE note_id = ? AND active = 1',(s.get_person_note(b).note_id,))]
    qa.assert_expected(1,len(mentions),'Advanced.Note.one_selected_occurrence')
    qa.assert_expected(c,mentions[0]['referenced_person_id'],'Advanced.Note.selected_target')
    qa.assert_expected(op,mentions[0]['created_operation_id'],'Advanced.Note.operation')
    expected_sources[op]=dict(kind='NOTE_REFERENCE',source=mentions[0]['mention_id'],raw=sorted([b,c]))
    check('Post-merge selected Note B -> C; literal A inert')
    # All three independent sources now support the same pair.
    del expected_sources['h01-2-metadata']
    del edges[tuple(sorted([b,c]))]['CO_OBSERVED']
    op = str(uuid.uuid4()); operations.append(op)
    m.correction(s, z, op, relations=[m.relation(b,c,'EXCLUDE')])
    check('EXCLUDE co-observation only; manual and directed Note survive')
    # Event mention is distinct from observed presence and relationship evidence.
    events[x]['mentioned_person_ids'] = [c]
    op = str(uuid.uuid4()); operations.append(op)
    m.correction(s, x, op, event_details=dict(event_notes='Selected @C', event_mentioned_person_ids=[c]))
    check('Event mention C at X adds no C occurrence or relationship')
    before = audit(s)
    for _ in range(2):
        s.rebuild_graph_projection(str(uuid.uuid4()))
        qa.assert_expected(before, audit(s), 'Advanced.rebuild.authority')
        check('Repeated supported rebuild from authoritative truth')
    return dict(people=people, events=events, edges=edges, canonical=canonical, raw=raw,
                source=a, survivor=b, third=c, original_manual_id=manual['evidence_id'])


def h02(s, date, proofs, visit=None):
    a, b = [s.create_person(n) for n in ('Recovery A','Recovery B')]
    a,b = a.person_id,b.person_id
    expected = event([a,b], 'X', 2)
    oid = m.finalize(s, 'h02', [s.get_person(a),s.get_person(b)], date,'X')
    events = {oid:expected}; people=[a,b]; canonical={a:a,b:b}
    edges={tuple(sorted(people)):{'CO_OBSERVED':1}}
    raw={oid:m.history(s,oid)}
    def check(action, fault=None):
        truth=dict(people=people,events=deepcopy(events),edges=deepcopy(edges),canonical=deepcopy(canonical))
        actual=verify(s,people,events,edges,canonical,raw,date)
        m.record(proofs,action,serial_truth(truth),actual)
        proofs[-1].update(provenance=deepcopy(raw),fault=fault,differences=[],
            stored_state={table:rows for table,rows in audit(s).items() if table in (
                'persons','observations','observation_participants','identity_corrections',
                'relationship_evidence','merge_operations','encounter_metadata_revisions',
                'encounter_participant_revisions','encounter_relation_decisions')},
            journal={op:s.get_operation(op) for op in ('h02-stale','h02-fault','h02-failed-merge','h02-merge-retry')})
        if visit: visit(s,truth,raw,action)
    check('Initial recoverable accepted pair')
    before=audit(s,include_journal=True)
    revision=s.get_encounter_read(oid)['revision']
    # Boundary 1: precommit rejection. The exception must actually occur.
    try:
        s.correct_encounter(oid,'h02-stale',expected_revision='stale-revision',event_details=dict(place_seen='Y'))
    except (ValueError,KeyError): pass
    else: raise AssertionError('Stale correction unexpectedly succeeded')
    qa.assert_expected(before,audit(s,include_journal=True),'Advanced.rejection.authority')
    qa.assert_expected(None,s.get_operation('h02-stale'),'Advanced.rejection.journal')
    check('Stale revision rejected without partial writes','precommit stale revision')
    # Boundary 2: graph write occurs inside the correction transaction after authority.
    with patch('sentriface.storage.sqlite_store._replace_graph_projection',side_effect=RuntimeError('advanced controlled graph fault')) as seam:
        try:
            s.correct_encounter(oid,'h02-fault',expected_revision=revision,event_details=dict(place_seen='Y'))
        except RuntimeError as exc:
            qa.assert_expected('advanced controlled graph fault',str(exc),'Advanced.fault')
        else: raise AssertionError('Injected correction did not fail')
        qa.assert_expected(1,seam.call_count,'Advanced.fault.reached')
    qa.assert_expected(before,audit(s,include_journal=True),'Advanced.rollback.authority')
    qa.assert_expected(None,s.get_operation('h02-fault'),'Advanced.rollback.journal')
    check('Correction transaction rolled back at graph boundary','monkeypatch graph publication')
    events[oid]['location']='Y'
    result=s.correct_encounter(oid,'h02-fault',expected_revision=revision,event_details=dict(place_seen='Y'))
    committed=audit(s)
    qa.assert_expected(result,s.correct_encounter(oid,'h02-fault',expected_revision=revision,event_details=dict(place_seen='Y')),'Advanced.correction.retry')
    qa.assert_expected(committed,audit(s),'Advanced.correction.exactly_once')
    check('Same correction ID retry succeeds once, repeated stale response returns original result')
    before=audit(s); reached=[]
    def fail(stage):
        reached.append(stage)
        if stage=='after_canonical_update': raise RuntimeError('advanced controlled canonical fault')
    try: s.execute_identity_merge(a,b,'h02-failed-merge',failure_injector=fail)
    except RuntimeError as exc: qa.assert_expected('advanced controlled canonical fault',str(exc),'Advanced.merge.fault')
    else: raise AssertionError('Injected merge did not fail')
    qa.assert_expected(['after_canonical_update'],reached,'Advanced.merge.seam')
    qa.assert_expected(before,audit(s),'Advanced.merge.rollback')
    qa.assert_expected('FAILED',s.get_operation('h02-failed-merge')['status'],'Advanced.merge.failed_audit')
    qa.assert_expected(None,s.get_merge_operation('h02-failed-merge'),'Advanced.merge.no_manifest')
    check('Merge rolled back; only durable FAILED attempt journal remains','existing after_canonical_update seam')
    try: s.execute_identity_merge(a,b,'h02-failed-merge')
    except ValueError as exc:
        assert 'new operation ID' in str(exc)
    else: raise AssertionError('Failed merge ID was accepted')
    people=[b]; canonical[a]=b; events[oid]['participant_ids']=[b]; edges={}
    result=s.execute_identity_merge(a,b,'h02-merge-retry')
    before=audit(s)
    qa.assert_expected(result,s.execute_identity_merge(a,b,'h02-merge-retry'),'Advanced.merge.replayed_response')
    qa.assert_expected(before,audit(s),'Advanced.merge.exactly_once')
    check('New merge ID recovery; lost-response replay has exactly one result')
    s.rebuild_graph_projection('h02-rebuild')
    check('Recovery rebuilt; canonical pair collapses without self edge')
    return dict(people=people,events=events,edges=edges,canonical=canonical,raw=raw)


def execute(args,evidence,report,journey):
    """Domain writes while stopped; genuine source restarts and authenticated HTTP
    projections at every transition. Browser navigation is not a UI merge claim.
    """
    import secrets
    from playwright.sync_api import sync_playwright
    import qa_browser as ui
    from sentriface.secure_storage import load_or_create_master_key
    from sentriface.storage.sqlite_store import SQLiteIdentityStore
    password=secrets.token_urlsafe(24)
    report.update(browser_errors=[],inference_executed=False,historical_proofs=[],browser_executed=False,domain_verified=False)
    with qa.disposable_data() as data:
        app=qa.Application(data,evidence,runtime='dev')
        try:
            with sync_playwright() as pw:
                try: browser=pw.chromium.launch(executable_path=args.chromium,headless=not args.headed)
                except Exception as exc: raise ui.Blocked('Chromium unavailable: '+str(exc)) from exc
                try:
                    app.start()
                    context,page=qa.browser_context(browser,app.url,report['browser_errors'])
                    try: ui.authenticate(page,password,first=True)
                    finally: context.close(); app.stop()
                    s=SQLiteIdentityStore(data/'sentriface.db',database_key=load_or_create_master_key(data)); s.initialize()
                    def visit(store,truth,raw,action):
                        app.start()
                        context,page=qa.browser_context(browser,app.url,report['browser_errors'])
                        try:
                            ui.authenticate(page,password,first=False,recovery=False)
                            read=lambda path: ui.get(context,path)
                            report['verified']=verify(store,truth['people'],truth['events'],truth['edges'],truth['canonical'],raw,args.date,read)
                            # The domain proof has already passed authored truth;
                            # HTTP must also preserve its exact verified provenance.
                            qa.assert_expected(report['historical_proofs'][-1]['observed'],report['verified'],'Advanced.HTTP.verified_provenance')
                            for pid,survivor in truth['canonical'].items():
                                person=read('/api/person?person_id='+pid)
                                qa.assert_expected(survivor,person['person']['person_id'],'Advanced.HTTP.effective_person')
                                original=read('/api/person?person_id='+pid+'&view=raw&include_archived=1')['person']
                                qa.assert_expected(pid,original['person_id'],'Advanced.HTTP.raw_person')
                                qa.assert_expected(survivor if pid != survivor else None,original['canonical_person_id'],'Advanced.HTTP.raw_canonical')
                            page.get_by_role('tab',name='Events',exact=True).click()
                            page.reload()
                            verify(store,truth['people'],truth['events'],truth['edges'],truth['canonical'],raw,args.date,read)
                            report['historical_proofs'][-1]['http_verified']=True
                        finally:
                            context.tracing.stop(path=str(evidence/('transition-'+str(len(report['historical_proofs']))+'.zip')))
                            context.close(); app.stop()
                    (h01 if journey=='H01' else h02)(s,args.date,report['historical_proofs'],visit)
                    report.update(browser_executed=True,domain_verified=True,restart_verified=True,rebuild_verified=True,
                        requested_size=dict(people=3 if journey=='H01' else 2,photos=0,encounters=3 if journey=='H01' else 1),
                        verification_boundary='Supported domain operations on stopped encrypted authority; browser login/navigation/refresh and live HTTP projection verification after source restart at each transition; no UI mutation or inference claim')
                    report['created_size']=dict(report['requested_size']); report['independently_verified_size']=dict(report['requested_size'])
                    qa.assert_expected([],report['browser_errors'],'Advanced.browser_errors')
                finally: browser.close()
        finally: app.stop()
    report['cleanup_completed']=True
