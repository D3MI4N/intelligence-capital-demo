---
doc_id: RAW-001
type: risk-survey
insured: NovaFreight Logistics BV
date: 2024-01-18
---

# Risk survey - NovaFreight Logistics BV

Commissioned by the placing broker, January 2024. Site visits at Rotterdam
HQ and three warehouses; remote review of IT estate.

## Operations
NovaFreight operates 14 warehouses across the Netherlands, Belgium and
northern Germany. Road freight and contract warehousing, revenue EUR 180M,
around 900 staff. Dispatch, inventory and dock scheduling run on a single
warehouse management system instance serving all sites.

## IT estate and controls
The WMS is hosted in a private data centre and operated jointly with the
software vendor under a managed-service agreement. The vendor holds a
standing remote-access channel for support and release management. There is
no network segregation between that channel and the WMS core: vendor
sessions terminate directly on production systems.

Staff access requires MFA. Patching follows a monthly cycle with emergency
provisions. Offline backups are taken daily and restoration is tested
quarterly; the last test (November 2023) restored the full WMS in 31 hours.

## Dependencies
A WMS outage halts dispatch at all 14 sites simultaneously. Manual
fallback exists for receiving but not for outbound scheduling. The insured
estimates tolerable downtime at 48 hours before contractual penalties with
retail customers begin to accrue.

## Surveyor remarks
Controls are appropriate for the segment. The single-instance WMS is the
dominant accumulation. The vendor relationship is long-standing; vendor
security posture was not in scope for this survey.
