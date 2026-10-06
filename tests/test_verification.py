"""Universal post-action verification contracts."""
from __future__ import annotations

import unittest

from saarthi.devices.base import ActionResult
from saarthi.verification import ActionVerifier, VerificationStatus, is_mutating


class ActionVerifierTests(unittest.TestCase):
    def test_read_action_success_itself_is_evidence(self):
        report = ActionVerifier({}).verify("file_padho", ActionResult.success("hello"))
        self.assertEqual(report.status, VerificationStatus.VERIFIED)
        self.assertFalse(report.mutating)

    def test_mutation_without_evidence_unverified_hai(self):
        report = ActionVerifier({}).verify("mail_bhejo", ActionResult.success("accepted"))
        self.assertEqual(report.status, VerificationStatus.UNVERIFIED)
        self.assertFalse(ActionVerifier({}).should_fail(report))

    def test_strict_mode_missing_evidence_fail_karta_hai(self):
        verifier = ActionVerifier({"SAARTHI_VERIFICATION_MODE": "strict"})
        report = verifier.verify("file_banao", ActionResult.success("saved"))
        self.assertTrue(verifier.should_fail(report))

    def test_explicit_positive_and_negative_evidence(self):
        verifier = ActionVerifier({})
        yes = verifier.verify("mail_bhejo", ActionResult.success("sent", verified=True))
        no = verifier.verify(
            "mail_bhejo",
            ActionResult.success("sent", verified=False, verification_message="Outbox mein nahi mila"),
        )
        self.assertEqual(yes.status, VerificationStatus.VERIFIED)
        self.assertEqual(no.status, VerificationStatus.FAILED)
        self.assertTrue(verifier.should_fail(no))

    def test_expected_observed_contract(self):
        verifier = ActionVerifier({})
        match = verifier.verify("file_banao", ActionResult.success(expected="abc", observed="abc"))
        mismatch = verifier.verify("file_banao", ActionResult.success(expected="abc", observed="xyz"))
        self.assertEqual(match.status, VerificationStatus.VERIFIED)
        self.assertEqual(mismatch.status, VerificationStatus.FAILED)

    def test_before_after_no_change_catches_false_success(self):
        verifier = ActionVerifier({})
        changed = verifier.verify("app_kholo", ActionResult.success(before_state="home", after_state="paytm"))
        unchanged = verifier.verify("app_kholo", ActionResult.success(before_state="home", after_state="home"))
        self.assertEqual(changed.status, VerificationStatus.VERIFIED)
        self.assertEqual(unchanged.status, VerificationStatus.FAILED)

    def test_failed_action_verification_skip_hoti_hai(self):
        report = ActionVerifier({}).verify("mail_bhejo", ActionResult.failure("network"))
        self.assertEqual(report.status, VerificationStatus.SKIPPED)

    def test_off_mode_and_invalid_default(self):
        off = ActionVerifier({"SAARTHI_VERIFICATION_MODE": "off"})
        self.assertEqual(
            off.verify("mail_bhejo", ActionResult.success()).status,
            VerificationStatus.SKIPPED,
        )
        invalid = ActionVerifier({"SAARTHI_VERIFICATION_MODE": "wrong"})
        self.assertEqual(invalid.mode.value, "basic")

    def test_critical_actions_mutating_classified_hain(self):
        for name in ("mail_bhejo", "file_banao", "command_chalao", "text_likho"):
            self.assertTrue(is_mutating(name), name)


if __name__ == "__main__":
    unittest.main()
