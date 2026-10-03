import uuid
from pathlib import Path
import sqlite3
import pytest
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.backup_service import BackupService


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('retired', [None, 'main', 'alias'])
@pytest.mark.parametrize('direction', ['alias-to-main', 'main-to-alias'])
def test_canonical_standing_assertion_preserves_history_across_merge(tmp_path, reverse, retired, direction):
    store = SQLiteIdentityStore(tmp_path/'sentriface.db', embedding_dim=2)
    store.initialize()
    main, alias, third = [store.create_person(name) for name in ('Main','Alias','Third')]
    def create(person, op):
        ids = [person.person_id,third.person_id]
        return store.create_manual_association(*(reversed(ids) if reverse else ids), op, actor={'display_name':op})
    first, second = create(main,'main-assertion'), create(alias,'alias-assertion')
    if retired:
        store.retire_manual_association((first if retired == 'main' else second)['evidence_id'], 'before-retire')
    source, target = (alias, main) if direction == 'alias-to-main' else (main,alias)
    with store._connect() as conn:
        before = [dict(r) for r in conn.execute("SELECT * FROM relationship_evidence ORDER BY evidence_id")]
    store.execute_identity_merge(source.person_id,target.person_id,'canonical-merge')
    with store._connect() as conn:
        after = [dict(r) for r in conn.execute("SELECT * FROM relationship_evidence ORDER BY evidence_id")]
    assert len(after) == len(before) == 2
    for old,new in zip(before,after):
        assert {k:v for k,v in old.items() if k not in ('active','deactivated_operation_id','deactivated_at')} == {k:v for k,v in new.items() if k not in ('active','deactivated_operation_id','deactivated_at')}
    active = [r for r in after if r['active']]
    assert len(active) == 1
    canonical = store.create_manual_association(third.person_id,source.person_id,'after-create')
    assert canonical['evidence_id'] == active[0]['evidence_id']
    restarted = SQLiteIdentityStore(store.db_path,embedding_dim=2);restarted.initialize()
    GlobalIdentityGraphService(restarted).rebuild_projection('manual-rebuild')
    backup_service = BackupService(store.db_path,tmp_path/'backups')
    backup = backup_service.create_backup();assert backup.restorable
    backup_service.restore_backup(backup.backup_id,str(uuid.uuid4()))
    restarted.retire_manual_association(active[0]['evidence_id'],'effective-retire')
    assert not restarted.get_person_neighbors(target.person_id)
    with restarted._connect() as conn:
        assert conn.execute("SELECT count(*) FROM relationship_evidence").fetchone()[0] == 2
    assert ReadOnlyIntegrityChecker(store.db_path).run().status == 'PASS'


def test_manual_collapse_and_retirement_preserve_other_evidence(tmp_path):
    store = SQLiteIdentityStore(tmp_path/'sentriface.db',embedding_dim=2);store.initialize()
    main,alias,third=[store.create_person(n) for n in ('Main','Alias','Third')]
    first=store.create_manual_association(main.person_id,third.person_id,'first')
    store.create_manual_association(alias.person_id,third.person_id,'second')
    graph=GlobalIdentityGraphService(store)
    graph.create_note(main.person_id,'Selected Third','note',mentioned_person_ids=[third.person_id])
    observation=store.create_observation('occurrence',participant_ids=[main.person_id,third.person_id])
    store._finalize_observation_without_graph_evidence(observation.observation_id,'finalize')
    graph.record_observation_evidence(observation.observation_id,'coobserved')
    store.execute_identity_merge(alias.person_id,main.person_id,'merge')
    store.retire_manual_association(first['evidence_id'],'retire')
    assert {kind for edge in store.get_person_neighbors(main.person_id) for kind in edge.evidence_types} == {'NOTE_REFERENCE','CO_OBSERVED'}
    graph.rebuild_projection('rebuild')
    assert {kind for edge in store.get_person_neighbors(main.person_id) for kind in edge.evidence_types} == {'NOTE_REFERENCE','CO_OBSERVED'}
    assert ReadOnlyIntegrityChecker(store.db_path).run().status == 'PASS'


def test_manual_retirement_does_not_expand_safe_merge_revert(tmp_path):
    from sentriface.errors import OperationRevertRefused
    store = SQLiteIdentityStore(tmp_path/'sentriface.db',embedding_dim=2);store.initialize()
    a, alias, c = [store.create_person(n) for n in ('Identity','Identity','Third')]
    store.create_manual_association(a.person_id,c.person_id,'first')
    store.create_manual_association(alias.person_id,c.person_id,'second')
    store.execute_identity_merge(alias.person_id,a.person_id,'merge')
    with pytest.raises(OperationRevertRefused,match='Manual Associations'):
        store.prepare_operation_revert('merge')


def test_manual_collision_retirement_rolls_back_with_merge(tmp_path):
    store = SQLiteIdentityStore(tmp_path/'sentriface.db',embedding_dim=2);store.initialize()
    a,alias,c=[store.create_person(n) for n in ('Main','Alias','Third')]
    store.create_manual_association(a.person_id,c.person_id,'first')
    store.create_manual_association(alias.person_id,c.person_id,'second')
    with store._connect() as conn:
        before=[dict(r) for r in conn.execute('SELECT * FROM relationship_evidence ORDER BY evidence_id')]
    def fail(stage):
        if stage=='after_graph_rebuild':raise RuntimeError('injected after retirement')
    with pytest.raises(RuntimeError,match='injected'):
        store.execute_identity_merge(alias.person_id,a.person_id,'failed-merge',failure_injector=fail)
    with store._connect() as conn:
        after=[dict(r) for r in conn.execute('SELECT * FROM relationship_evidence ORDER BY evidence_id')]
    assert before==after
    assert store.get_person(alias.person_id).canonical_person_id is None
    assert store.get_operation('failed-merge')['status']=='FAILED'
