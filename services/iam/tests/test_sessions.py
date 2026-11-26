"""Run against a migrated disposable mis_iam database, not a live installation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import secrets
import unittest
from uuid import uuid4, uuid7

from grpc import StatusCode
from contracts.grpc.v1 import iam_pb2 as api

from ..sessions import Authority, Denied, connect_db


class Sessions(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(UTC)
        self.iam = Authority(connect_db, secrets.token_bytes(32), lambda: self.now)

    def denied(self, fn, *args, status=StatusCode.UNAUTHENTICATED):
        with self.assertRaises(Denied) as error:
            fn(*args)
        self.assertEqual(error.exception.status, status)

    def guest(self):
        return self.iam.guest(str(uuid4()), '')

    def test_guest_key_is_not_a_credential(self):
        key = str(uuid4())
        first = self.iam.guest(key, '')
        second = self.guest()
        self.assertTrue(first.principal.is_guest)
        self.assertNotEqual(first.principal.actor.subject_id, second.principal.actor.subject_id)
        self.assertEqual(first.principal, self.iam.authenticate(first.access_token))
        self.denied(self.iam.guest, key, second.access_token, status=StatusCode.ALREADY_EXISTS)
        self.assertEqual(self.iam.guest(key, first.access_token), first)
        self.denied(self.iam.authenticate, first.principal.actor.subject_id)
        self.denied(self.iam.authenticate, first.refresh_token)

    def test_expiry_rotation_and_absolute_limit(self):
        first = self.guest()
        self.assertEqual(first.access_expires_at.ToDatetime(UTC), self.now + timedelta(hours=168))
        deadline = self.now + timedelta(days=30)
        self.now += timedelta(hours=168)
        self.denied(self.iam.authenticate, first.access_token)
        new = self.iam.rotate(first.refresh_token)
        self.assertEqual(first.principal.actor, new.principal.actor)
        self.assertNotEqual(first.refresh_token, new.refresh_token)
        self.now = deadline - timedelta(seconds=1)
        last = self.iam.rotate(new.refresh_token)
        self.assertEqual(last.access_expires_at.ToDatetime(UTC), deadline)
        self.assertEqual(last.refresh_expires_at.ToDatetime(UTC), deadline)
        self.now = deadline
        self.denied(self.iam.rotate, last.refresh_token)
        self.denied(self.iam.authenticate, last.access_token)

    def test_only_current_pair_is_valid_after_rotation(self):
        first = self.guest()
        second = self.iam.rotate(first.refresh_token)
        self.denied(self.iam.authenticate, first.access_token)
        self.denied(self.iam.rotate, 'unrelated-invalid-secret')
        self.assertEqual(self.iam.authenticate(second.access_token), first.principal)
        self.iam.end(second.access_token)
        self.denied(self.iam.rotate, second.refresh_token)

    def test_concurrent_refresh_replay_revokes_family(self):
        first = self.guest()
        def rotate():
            try:
                return self.iam.rotate(first.refresh_token)
            except Denied:
                return None
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(lambda _: rotate(), range(2)))
        winners = [pair for pair in responses if pair is not None]
        self.assertEqual(len(winners), 1)
        self.denied(self.iam.authenticate, winners[0].access_token)
        self.denied(self.iam.rotate, winners[0].refresh_token)

    def test_decision_binds_actor_session_action_and_owner(self):
        a, b = self.guest(), self.guest()
        check = api.CheckAccessRequest(action='getOperation', resource_owner_subject_id=a.principal.actor.subject_id)
        check.context.actor.CopyFrom(a.principal.actor)
        check.resource.resource_type = 'operation'
        check.resource.resource_id = str(uuid7())
        decision = self.iam.check(check)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.expires_at.ToDatetime(UTC), self.now + timedelta(seconds=5))
        check.resource_owner_subject_id = b.principal.actor.subject_id
        self.assertFalse(self.iam.check(check).allowed)
        check.context.actor.subject_id = b.principal.actor.subject_id
        self.assertFalse(self.iam.check(check).allowed)
        check.context.actor.CopyFrom(a.principal.actor)
        check.resource_owner_subject_id = a.principal.actor.subject_id
        check.action = 'publishArticle'
        self.assertFalse(self.iam.check(check).allowed)
        self.iam.end(a.access_token)
        check.action = 'getOperation'
        self.assertEqual(self.iam.check(check).reason_code, 'ACCESS_REVOKED')

    def test_unblocking_does_not_revive_a_family(self):
        email = f'{uuid4()}@example.test'
        self.iam.provision(email, 'synthetic-password', 'admin')
        a = self.iam.sign_in(email, 'synthetic-password')
        with self.iam.transaction() as db:
            db.execute('UPDATE principals SET blocked_at=now() WHERE id=%s', (a.principal.actor.subject_id,))
        self.denied(self.iam.sign_in, email, 'synthetic-password')
        with self.iam.transaction() as db:
            db.execute('UPDATE principals SET blocked_at=NULL WHERE id=%s', (a.principal.actor.subject_id,))
        self.denied(self.iam.authenticate, a.access_token)
        self.denied(self.iam.rotate, a.refresh_token)

    def test_staff_logout_does_not_revoke_other_device(self):
        email = f'{uuid4()}@example.test'
        self.iam.provision(email, 'synthetic-password', 'editor')
        self.denied(self.iam.sign_in, email, 'wrong')
        self.denied(self.iam.sign_in, 'absent@example.test', 'wrong')
        a = self.iam.sign_in(email.upper(), 'synthetic-password')
        b = self.iam.sign_in(email, 'synthetic-password')
        self.assertFalse(a.principal.is_guest)
        self.assertEqual(list(a.principal.roles), [3])
        self.assertEqual(a.principal.actor.subject_id, b.principal.actor.subject_id)
        self.iam.end(a.access_token)
        self.denied(self.iam.authenticate, a.access_token)
        self.denied(self.iam.rotate, a.refresh_token)
        self.assertEqual(self.iam.authenticate(b.access_token), b.principal)
