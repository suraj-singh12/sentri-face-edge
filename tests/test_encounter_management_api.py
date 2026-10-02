from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from sentriface.api_server import create_server
from sentriface.auth import AUTH_COOKIE_NAME
from sentriface.models import DetectedFace, FaceBox, MatchDecision, PendingAddition, QualityReport, QualityStatus
from sentriface.integrity import ReadOnlyIntegrityChecker


class EncounterManagementApiTest(unittest.TestCase):
    def test_permissions_tombstone_history_corrections_and_manual_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            server = create_server(port=0, data_dir=Path(temp) / 'data', runtime='dev', debug=False)
            admin, token = server.auth.signup_initial('admin-test', 'Administrator', 'administrator test password')
            cookies = {'administrator': f'{AUTH_COOKIE_NAME}={token}'}
            for role in ('viewer', 'operator', 'custodian', 'technician'):
                server.auth.create_user(admin, f'{role}-test', role, f'{role} test password secure', [role])
                _, role_token = server.auth.login(f'{role}-test', f'{role} test password secure')
                cookies[role] = f'{AUTH_COOKIE_NAME}={role_token}'
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                store = server.engine.store
                a, b = [store.create_person(name) for name in ('Alice', 'Bob')]
                faces = []
                for index, person in enumerate((a, b)):
                    pending_id = f'api-{index}'
                    vector = tuple([1.0-index*.2, index*.2] + [0.0]*(server.engine.config.embedding_dim-2))
                    store.save_pending_addition(PendingAddition(pending_id=pending_id, source_image=f'/managed/{pending_id}.jpg',
                        face=DetectedFace(FaceBox(1, 1, 10, 10, .9), .9), vector=vector, matches=[], decision=MatchDecision.UNKNOWN,
                        quality=QualityReport(QualityStatus.GOOD, .9)))
                    faces.append({'face_id': pending_id, 'staged_face_type': 'PENDING_ADDITION', 'staged_face_id': pending_id})
                store.create_photo_review('api-encounter', 'api-image', faces, media_path='/managed/api-0.jpg')
                for index, person in enumerate((a, b)):
                    store.set_photo_review_face_decision('api-encounter', f'api-{index}', 'ACCEPT_EXISTING_PERSON', person_id=person.person_id)
                oid = store.complete_photo_review('api-encounter', str(uuid.uuid4()))['observation_id']
                def request(method, path, role='administrator', payload=None):
                    connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=20)
                    headers = {'X-SentriFace-Session': server.session_token, 'Cookie': cookies[role], 'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{server.server_address[1]}'}
                    connection.request(method, path, body=json.dumps(payload) if payload is not None else None, headers=headers)
                    response = connection.getresponse()
                    body = json.loads(response.read())
                    connection.close()
                    return response.status, body
                for role in cookies:
                    self.assertEqual(request('GET', f'/api/encounter?observation_id={oid}', role)[0], 200)
                detail = request('GET', f'/api/encounter?observation_id={oid}')[1]
                correction = {'observation_id': oid, 'operation_id': str(uuid.uuid4()), 'expected_revision': detail['revision'],
                    'event_details': {'place_seen': 'Agra', 'event_mentioned_person_ids': [b.person_id]}}
                for role in ('viewer', 'operator', 'technician'):
                    self.assertEqual(request('POST', '/api/encounter-correct', role, correction)[0], 403)
                status, result = request('POST', '/api/encounter-correct', 'custodian', correction)
                self.assertEqual(status, 200, result)
                self.assertEqual(request('POST', '/api/encounter-correct', 'custodian', correction)[1], result)
                for role in ('viewer', 'technician'):
                    self.assertEqual(request('POST', '/api/encounter-attach-media', role, {})[0], 403)
                association = {'first_person_id': a.person_id, 'second_person_id': b.person_id, 'operation_id': str(uuid.uuid4())}
                self.assertEqual(request('POST', '/api/person-association', 'viewer', association)[0], 403)
                status, manual = request('POST', '/api/person-association', 'operator', association)
                self.assertEqual(status, 200, manual)
                self.assertEqual(request('POST', '/api/person-association', 'operator', association)[1], manual)
                store.create_note(a.person_id, 'Remember @Bob', str(uuid.uuid4()), mentioned_person_ids=[b.person_id])
                store.soft_delete_person(b.person_id, str(uuid.uuid4()))
                for path in ('/api/persons', '/api/encounters', f'/api/encounter?observation_id={oid}',
                             f'/api/person?person_id={a.person_id}', f'/api/person?person_id={b.person_id}&view=raw&include_archived=1',
                             f'/api/person-graph?person_id={a.person_id}&version=1', '/api/world-graph?version=2'):
                    status, history = request('GET', path)
                    self.assertEqual(status, 200, (path, history))
                    self.assertNotIn('Unknown person:', json.dumps(history))
                status, profile = request('GET', f'/api/person?person_id={a.person_id}')
                self.assertEqual(profile['relationships'][0]['person']['lifecycle_status'], 'DELETED')
                self.assertEqual(profile['relationships'][0]['person']['allowed_actions'], ['VIEW_HISTORY'])
                removed = request('POST', '/api/person-association-remove', 'operator', {'evidence_id': manual['evidence_id'], 'operation_id': str(uuid.uuid4())})
                self.assertEqual(removed[0], 200, removed)
                self.assertTrue(any('CO_OBSERVED' in item.evidence_types for item in store.get_person_neighbors(a.person_id)))
                report = ReadOnlyIntegrityChecker(store.db_path, database_key=store.database_key).run()
                self.assertEqual(report.findings, ())
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)
