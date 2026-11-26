"""The IAM database, not a JWT claim or a BFF cache, is the session authority."""
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import os
from pathlib import Path
import secrets
from uuid import UUID, uuid7

from google.protobuf.timestamp_pb2 import Timestamp
from grpc import StatusCode
from pg8000.dbapi import connect, DatabaseError

from contracts.common.v1.metadata_pb2 import ActorContext
from contracts.grpc.v1 import iam_pb2 as api

ACCESS_TTL = timedelta(hours=168)
FAMILY_TTL = timedelta(days=30)
POLICY = 'demo-medical-v1'
CABINET_ACTIONS = {
    'getOnboarding', 'finishOnboarding', 'listMedications', 'addMedication', 'updateMedication',
    'stopMedication', 'listDoses', 'markIntake', 'getReminderSettings', 'updateReminderSettings',
    'listNotifications', 'readNotification', 'listDiaryEntries', 'getDiaryEntry', 'createDiaryEntry',
    'replaceDiaryEntry', 'deleteDiaryEntry', 'listScreeningResults',
}
ROLES = {'patient': api.USER_ROLE_PATIENT, 'admin': api.USER_ROLE_ADMIN, 'editor': api.USER_ROLE_EDITOR}
# The BFF owns the synthetic resource partitions. No service-wide read permission.
GUEST_ACTIONS = {
    'subject': {'startScreening'},
    'screening': {'getScreening', 'saveAnswer', 'continueAfterRedFlag', 'completeScreening', 'abandonScreening', 'getLatestResult'},
    'result': {'getExactResult', 'requestPdf'},
    'report': {'getReport', 'downloadOwnPdf'},
    'operation': {'getOperation'},
}


def can_access(principal, action, resource_type, target, owner):
    subject = principal.actor.subject_id
    if owner != subject or (resource_type in ('subject', 'cabinet') and target != subject):
        return False
    patient = list(principal.roles) == [api.USER_ROLE_PATIENT]
    if resource_type == 'cabinet':
        return patient and principal.has_medical_consent and action in CABINET_ACTIONS
    return (principal.is_guest or patient) and action in GUEST_ACTIONS.get(resource_type, ())


def connect_db():
    return connect(host=os.environ['PGHOST'], database='mis_iam', user='mis_iam_app', timeout=4,
                   password=Path('/run/secrets/db-password').read_text().strip())


def ts(at):
    value = Timestamp()
    value.FromDatetime(at)
    return value


def digest(token):
    return hashlib.sha256(token.encode()).digest()


def password_digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=3, maxmem=64 << 20, dklen=32)


class Denied(Exception):
    def __init__(self, status=StatusCode.UNAUTHENTICATED):
        self.status = status


def identifier(value, version=None):
    try:
        parsed = UUID(value)
        if version and parsed.version != version:
            raise ValueError
        return parsed
    except ValueError:
        raise Denied(StatusCode.INVALID_ARGUMENT) from None


class Authority:
    def __init__(self, connect_db, key, clock=lambda: datetime.now(UTC)):
        if len(key) < 32:
            raise ValueError('IAM key must be at least 256 bits')
        self.connect_db, self.key, self.clock = connect_db, key, clock

    @contextmanager
    def transaction(self):
        with closing(self.connect_db()) as db:
            yield db.cursor()
            db.commit()  # Closing an uncommitted connection rolls back, including on errors.

    def mac(self, purpose, value):
        return hmac.digest(self.key, f'{purpose}:{value}'.encode(), 'sha256')

    def email_key(self, email):
        return self.mac('staff-email', email.strip().casefold())

    def insert_account(self, cur, email, password, role, consent=None, guest_id=None):
        if role not in ROLES or not email.strip() or len(email) > 254 or not 12 <= len(password) <= 256:
            raise Denied(StatusCode.INVALID_ARGUMENT)
        salt = secrets.token_bytes(16)
        encoded = 'scrypt-v1:' + salt.hex() + ':' + password_digest(password, salt).hex()
        # 'staff' is the legacy storage discriminator for password accounts; authorization uses principal_roles.
        params = (self.email_key(email), encoded, consent)
        if guest_id:
            try:
                cur.execute("UPDATE principals SET kind='staff',email_hmac=%s,password_hash=%s,consent_version=%s WHERE id=%s AND kind='guest' RETURNING id", (*params, guest_id))
            except DatabaseError as exc:
                detail = exc.args[0] if exc.args else None
                if isinstance(detail, dict) and detail.get('C') == '23505':
                    raise Denied(StatusCode.ALREADY_EXISTS) from None
                raise
        else:
            cur.execute("INSERT INTO principals (kind,email_hmac,password_hash,consent_version) VALUES ('staff',%s,%s,%s) ON CONFLICT (email_hmac) DO NOTHING RETURNING id", params)
        row = cur.fetchone()
        if not row:
            raise Denied(StatusCode.ALREADY_EXISTS)
        self.assign(cur, row[0], role)
        return row[0]

    def assign(self, cur, subject, role):
        cur.execute('INSERT INTO roles(code) VALUES (%s) ON CONFLICT DO NOTHING', (role,))
        cur.execute('UPDATE principal_roles SET revoked_at=now() WHERE principal_id=%s AND revoked_at IS NULL', (subject,))
        cur.execute("INSERT INTO principal_roles(principal_id,role_id,expires_at) SELECT %s,id,'infinity' FROM roles WHERE code=%s ON CONFLICT (principal_id,role_id) DO UPDATE SET revoked_at=NULL,expires_at='infinity'", (subject, role))

    def bootstrap(self, email, password):
        if not email and not password:
            return
        with self.transaction() as cur:
            cur.execute('INSERT INTO admin_bootstrap VALUES (true) ON CONFLICT DO NOTHING RETURNING singleton')
            if not cur.fetchone():
                return
            # Upgrade from an installation with an existing administrator: do not
            # use bootstrap as an alternative path to creating a second admin.
            cur.execute("SELECT 1 FROM principal_roles p JOIN roles r ON r.id=p.role_id WHERE r.code='admin' LIMIT 1")
            if not cur.fetchone():
                self.insert_account(cur, email, password, 'admin')

    def register(self, req):
        key = identifier(req.request_id)
        if req.consent_version != POLICY:
            raise Denied(StatusCode.INVALID_ARGUMENT)
        with self.transaction() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(%s)', (int.from_bytes(key.bytes[:8], signed=True),))
            cur.execute('SELECT id, principal_id, generation, access_expires_at, expires_at, revoked_at FROM auth_sessions WHERE registration_request_id=%s FOR UPDATE', (key,))
            old = cur.fetchone()
            if old:
                session, subject, generation, access_end, end, revoked = old
                try:
                    verified = self.verify_password(cur, req.email, req.password)
                except Denied:
                    raise Denied(StatusCode.FAILED_PRECONDITION) from None
                if verified != subject:
                    raise Denied(StatusCode.FAILED_PRECONDITION)
                if revoked or self.clock() >= min(access_end, end):
                    raise Denied()
                return self.pair(self.principal(cur, subject, session, end, self.clock()), generation, access_end)
            guest_id = None
            if req.guest_access_token:
                actor = self.access(cur, req.guest_access_token)
                if actor.is_guest:
                    guest_id = actor.actor.subject_id
            subject = self.insert_account(cur, req.email, req.password, 'patient', POLICY, guest_id)
            if guest_id:
                cur.execute('UPDATE auth_sessions SET revoked_at=now() WHERE principal_id=%s AND revoked_at IS NULL', (subject,))
            tokens = self.create(cur, subject)
            cur.execute('UPDATE auth_sessions SET registration_request_id=%s WHERE id=%s', (key, tokens.principal.actor.session_id))
            return tokens

    def set_role(self, req):
        role = next((name for name, value in ROLES.items() if value == req.role), None)
        with self.transaction() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(17704488)')
            actor = self.access(cur, req.access_token)
            if api.USER_ROLE_ADMIN not in actor.roles:
                raise Denied(StatusCode.PERMISSION_DENIED)
            cur.execute('SELECT id,consent_version FROM principals WHERE email_hmac=%s FOR UPDATE', (self.email_key(req.email),))
            row = cur.fetchone()
            if not row:
                raise Denied(StatusCode.NOT_FOUND)
            if not role or str(row[0]) == actor.actor.subject_id or (role == 'patient' and row[1] != POLICY):
                raise Denied(StatusCode.INVALID_ARGUMENT)
            self.assign(cur, row[0], role)
            cur.execute('UPDATE auth_sessions SET revoked_at=now() WHERE principal_id=%s AND revoked_at IS NULL', (row[0],))

    def withdraw_consent(self, token):
        with self.transaction() as cur:
            actor = self.access(cur, token)
            if list(actor.roles) != [api.USER_ROLE_PATIENT]:
                raise Denied(StatusCode.PERMISSION_DENIED)
            cur.execute('UPDATE principals SET consent_version=NULL WHERE id=%s', (actor.actor.subject_id,))

    def principal(self, cur, subject, session, expires, at):
        cur.execute('''SELECT p.kind,r.code,p.consent_version FROM principals p
            LEFT JOIN principal_roles pr ON pr.principal_id=p.id AND pr.revoked_at IS NULL AND pr.expires_at>%s
            LEFT JOIN roles r ON r.id=pr.role_id WHERE p.id=%s AND p.blocked_at IS NULL''', (at, subject))
        row = cur.fetchone()
        if not row or (row[0] == 'staff' and row[1] not in ROLES):
            raise Denied()
        return api.Principal(actor=ActorContext(subject_id=str(subject), session_id=str(session)), is_guest=row[0] == 'guest',
                             roles=[] if row[0] == 'guest' else [ROLES[row[1]]], session_expires_at=ts(expires),
                             has_medical_consent=row[1] == 'patient' and row[2] == POLICY)

    def pair(self, principal, generation, access_end):
        # Recover the current pair for a proven guest retry, without storing bearer secrets.
        context = f'{principal.actor.session_id}:{generation}'
        return api.TokenPair(access_token=self.mac('access', context).hex(), refresh_token=self.mac('refresh', context).hex(),
                             access_expires_at=ts(access_end), refresh_expires_at=principal.session_expires_at, principal=principal)

    def create(self, cur, subject, request_id=None):
        # Order session creation against concurrent account blocking. A block
        # committed after this lock must also revoke the newly inserted row.
        cur.execute('SELECT id FROM principals WHERE id=%s FOR SHARE', (subject,))
        session, at = uuid7(), self.clock()
        principal = self.principal(cur, subject, session, at + FAMILY_TTL, at)
        tokens = self.pair(principal, 0, at + ACCESS_TTL)
        refresh = digest(tokens.refresh_token)
        cur.execute('''INSERT INTO auth_sessions(id,principal_id,issued_at,expires_at,access_expires_at,
                       access_token_hash,refresh_token_hash,guest_request_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (session, subject, at, at + FAMILY_TTL, at + ACCESS_TTL, digest(tokens.access_token), refresh, request_id))
        cur.execute('INSERT INTO session_refresh_tokens VALUES (%s,%s)', (refresh, session))
        return tokens

    def guest(self, request_id, access):
        key = identifier(request_id)
        with self.transaction() as cur:
            # Serialize creators of the same public idempotency key across replicas.
            cur.execute('SELECT pg_advisory_xact_lock(%s)', (int.from_bytes(key.bytes[:8], signed=True),))
            cur.execute('SELECT id,principal_id,generation,access_expires_at,expires_at,access_token_hash,revoked_at FROM auth_sessions WHERE guest_request_id=%s FOR UPDATE', (key,))
            old = cur.fetchone()
            if old:
                session, subject, generation, access_end, end, proof, revoked = old
                if not hmac.compare_digest(digest(access), proof):
                    raise Denied(StatusCode.ALREADY_EXISTS)
                at = self.clock()
                if revoked or at >= min(access_end, end):
                    raise Denied()
                return self.pair(self.principal(cur, subject, session, end, at), generation, access_end)
            cur.execute("INSERT INTO principals(kind) VALUES ('guest') RETURNING id")
            return self.create(cur, cur.fetchone()[0], key)

    def verify_password(self, cur, email, password):
        if not 0 < len(email) <= 254 or not 0 < len(password) <= 256:
            raise Denied()
        cur.execute("SELECT id,password_hash FROM principals WHERE email_hmac=%s AND kind='staff'", (self.email_key(email),))
        row = cur.fetchone()
        salt, expected = bytes(16), bytes(32)
        if row and row[1].startswith('scrypt-v1:'):
            try:
                salt, expected = map(bytes.fromhex, row[1].split(':')[1:])
            except ValueError:
                raise Denied() from None
        if not hmac.compare_digest(password_digest(password, salt), expected) or not row:
            raise Denied()
        return row[0]

    def sign_in(self, email, password):
        with self.transaction() as cur:
            return self.create(cur, self.verify_password(cur, email, password))

    def access(self, cur, token):
        cur.execute('''SELECT id,principal_id,expires_at,access_expires_at,revoked_at FROM auth_sessions
                       WHERE access_token_hash=%s FOR UPDATE''', (digest(token),))
        row = cur.fetchone()
        at = self.clock()
        if not row or row[4] or at >= min(row[2], row[3]):
            raise Denied()
        return self.principal(cur, row[1], row[0], row[2], at)

    def authenticate(self, token):
        with self.transaction() as cur:
            return self.access(cur, token)

    def end(self, token):
        with self.transaction() as cur:
            principal = self.access(cur, token)
            cur.execute('UPDATE auth_sessions SET revoked_at=%s WHERE id=%s', (self.clock(), principal.actor.session_id))

    def rotate(self, token):
        presented = digest(token)
        with self.transaction() as cur:
            cur.execute('''SELECT s.id,s.principal_id,s.expires_at,s.revoked_at,s.refresh_token_hash,s.generation
                FROM session_refresh_tokens t JOIN auth_sessions s ON s.id=t.session_id WHERE t.token_hash=%s FOR UPDATE OF s''', (presented,))
            row = cur.fetchone()
            at = self.clock()
            if not row or row[3] or at >= row[2]:
                raise Denied()
            session, subject, end, _, current, generation = row
            if hmac.compare_digest(current, presented):
                access_end = min(end, at + ACCESS_TTL)
                tokens = self.pair(self.principal(cur, subject, session, end, at), generation + 1, access_end)
                refresh = digest(tokens.refresh_token)
                cur.execute('UPDATE auth_sessions SET access_token_hash=%s,refresh_token_hash=%s,access_expires_at=%s,generation=generation+1 WHERE id=%s',
                            (digest(tokens.access_token), refresh, access_end, session))
                cur.execute('INSERT INTO session_refresh_tokens VALUES (%s,%s)', (refresh, session))
                return tokens
            cur.execute('UPDATE auth_sessions SET revoked_at=%s WHERE id=%s', (at, session))
        # A replay must COMMIT the revocation before returning UNAUTHENTICATED.
        raise Denied()

    def check(self, request):
        actor, resource = request.context.actor, request.resource
        subject, session = identifier(actor.subject_id, 7), identifier(actor.session_id, 7)
        target = identifier(resource.resource_id, 7)
        with self.transaction() as cur:
            cur.execute('SELECT principal_id,expires_at,revoked_at FROM auth_sessions WHERE id=%s AND access_token_hash=%s AND access_expires_at>%s FOR SHARE', (session, digest(request.access_token), self.clock()))
            row = cur.fetchone()
            at = self.clock()
            live = row and str(row[0]) == str(subject) and not row[2] and at < row[1]
            allowed = False
            if live:
                try:
                    p = self.principal(cur, subject, session, row[1], at)
                    allowed = can_access(p, request.action, resource.resource_type, str(target), request.resource_owner_subject_id)
                except Denied:
                    pass
            reason = 'ALLOW' if allowed else ('ACCESS_DENIED' if live else 'ACCESS_REVOKED')
            cur.execute('''INSERT INTO access_audit(subject_id,session_id,resource_type,resource_id,action,allowed,reason_code,evaluated_at,audience)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'bff') RETURNING id''',
                        (subject, session, resource.resource_type, target, request.action, allowed, reason, at))
            expires = min(at + timedelta(seconds=5), row[1]) if allowed else at
            return api.AccessDecision(decision_id=str(cur.fetchone()[0]), allowed=allowed, reason_code=reason,
                                      evaluated_at=ts(at), expires_at=ts(expires))
