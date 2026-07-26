---
doc_id: RAW-003
type: forensics-report
claim: CLM-2024-042
date: 2024-08-02
---

# Forensics final report - NovaFreight WMS incident

Independent forensics engagement, final version 2024-08-02. Interim
findings of 2024-06-20 are superseded.

## Intrusion path
Initial compromise occurred at the WMS software vendor on 2024-06-07.
Credentials of a vendor support engineer were obtained through a targeted
phishing message impersonating the vendor's identity provider. The
attacker authenticated to the vendor's remote-support gateway and, from
there, used the standing managed-service channel into the insured's WMS
production environment. Lateral movement was confined to the WMS estate.
Ransomware was staged on 2024-06-08 and detonated at 02:47 CET on
2024-06-09.

## Insured control performance
The insured's scheduled controls operated as designed throughout:
- MFA was enforced on all insured staff accounts; no insured credential
  was compromised.
- The monthly patching cycle was current; no unpatched vulnerability on
  insured systems was exploited.
- Offline backups were unaffected. Restoration began 2024-06-10 and
  completed 2024-06-18, within one restoration cycle of the tested 31-hour
  benchmark per site group.

## Root cause
The intrusion succeeded exclusively through vendor-side infrastructure and
the un-segregated standing access channel. No failure of a control listed
in the insured's policy schedule contributed to the loss.
