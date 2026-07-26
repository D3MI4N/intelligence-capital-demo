# Entity types - controlled vocabulary

| type          | examples                                   |
|---------------|--------------------------------------------|
| RiskClass     | cyber-logistics                            |
| Insured       | NovaFreight Logistics BV                   |
| Policy        | policy bound under SUB-2024-018            |
| Clause        | CY-EX-04, CY-EX-01                         |
| Peril         | ransomware, vendor-compromise              |
| Case          | SUB-2024-018, CLM-2024-042, SUB-2025-007   |
| Lesson        | L-001 vendor standing access               |
| Skill         | SK-003 precedent search                    |
| Document      | wiki/claims/CLM-2024-042/coverage.md       |

Node IDs are "Type:key" - Case:CLM-2024-042, Clause:CY-EX-04,
Insured:novafreight-logistics-bv. Cite them as written.

# Edge types - controlled vocabulary

Every edge is derived from structure a human wrote: a frontmatter field, a
wikilink, an identifier, or a source note locator line.

| relation          | from -> to             | derived from                     |
|-------------------|------------------------|----------------------------------|
| belongs_to        | Document -> Case       | frontmatter case_id              |
| about_case        | Document -> Case       | frontmatter claim or submission  |
| insured_by        | Case -> Insured        | frontmatter insured              |
| mentions_insured  | Document -> Insured    | frontmatter insured, no case     |
| in_class          | Case -> RiskClass      | frontmatter class                |
| applies_to_class  | Document -> RiskClass  | frontmatter domain               |
| involves_peril    | Case -> Peril          | frontmatter peril, peril_focus   |
| linked_claim      | Case -> Case           | frontmatter linked_claim         |
| linked_submission | Case -> Case           | frontmatter linked_submission    |
| related_case      | Case -> Case           | wikilink between two cases       |
| references        | Document -> Document   | wikilink target path             |
| derived_from      | Document -> Document   | frontmatter original, Locator:   |
| mentions_clause   | Document, Case -> Clause | CY-EX-* in the text            |
| records_lesson    | Document -> Lesson     | L-* in the text                  |
| has_lesson        | Case -> Lesson         | L-* in a case document           |
| defines_skill     | Document -> Skill      | frontmatter skill_id             |
| mentions_skill    | Document -> Skill      | SK-* in the text                 |
