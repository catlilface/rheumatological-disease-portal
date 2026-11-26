import unittest
from contracts.grpc.v1 import iam_pb2 as api
from ..sessions import can_access


class Policy(unittest.TestCase):
    def test_role_owner_and_action_are_all_required(self):
        for role in (None, api.USER_ROLE_PATIENT, api.USER_ROLE_EDITOR, api.USER_ROLE_ADMIN):
            with self.subTest(role=role):
                p = api.Principal(is_guest=role is None, roles=[] if role is None else [role], has_medical_consent=role == api.USER_ROLE_PATIENT)
                p.actor.subject_id = 'one'
                self.assertEqual(can_access(p, 'getExactResult', 'result', 'r', 'one'), role in (None, api.USER_ROLE_PATIENT))
                self.assertEqual(can_access(p, 'listMedications', 'cabinet', 'one', 'one'), role == api.USER_ROLE_PATIENT)
                self.assertFalse(can_access(p, 'getExactResult', 'result', 'r', 'two'))
                self.assertFalse(can_access(p, 'listMedications', 'cabinet', 'two', 'one'))
                self.assertFalse(can_access(p, 'unknown', 'result', 'r', 'one'))
                p.has_medical_consent = False
                self.assertFalse(can_access(p, 'listMedications', 'cabinet', 'one', 'one'))
