---
case_id: CLM-2024-042
updated: 2024-09-15
---

# Coverage analysis - the CY-EX-04 dispute

## Position A - exclusion applies (initial insurer position)
CY-EX-04 excludes loss caused by failure to maintain agreed security
controls. The intrusion succeeded because access controls failed. On a
broad reading, the failure sits inside the exclusion regardless of whose
controls failed.

## Position B - exclusion does not apply (insured position)
The controls that failed belong to the vendor. The policy schedule lists
the insured's controls (MFA, offline backups, patching cadence) - all were
in place and operating, confirmed by forensics. CY-EX-04 as worded assumes
systems under the insured's control; it does not allocate vendor risk.

## Resolution
Position B prevailed (decision D-002). The submission file itself had
flagged the gap: SUB-2024-018 coverage-or-appetite.md recorded that
CY-EX-04's assumption of insured-controlled systems was never examined
against the joint vendor operation of the WMS. An ambiguous exclusion is
read against its drafter.

Assessment: this is a wording gap, not a handling error. The fix belongs
upstream in appetite and wording for vendor-operated systems - see
lessons.md.
