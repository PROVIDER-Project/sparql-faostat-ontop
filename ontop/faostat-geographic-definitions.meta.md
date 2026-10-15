# FAOSTAT geographic definitions and country-link policy

## Sources

- Publisher: Food and Agriculture Organization of the United Nations (FAO).
- Definitions retrieved: 2026-10-15; classification edition unspecified.
- Official page: https://www.fao.org/faostat/en/#definitions
- Official country concordance API: https://faostatservices.fao.org/api/v1/en/definitions/types/area
- Official membership API: https://faostatservices.fao.org/api/v1/en/definitions/types/areagroup
- Browser CSV exports were used; the APIs require the website's guest authentication.
- Mirror coordinates: `org.aksw.data.thirdparty.org.fao.faostat:geographic-definitions-20261015:1`.
- This mirror is a temporary retrieval location, not a public service commitment.
  Override `GEOGRAPHIC_DEFINITIONS_BASE_URL` on the Compose fetch service when
  migrating the same artifact; clear the affected cached definitions first.
- POM: https://maven.inf-ai.duckdns.org/releases/org/aksw/data/thirdparty/org/fao/faostat/geographic-definitions-20261015/1/geographic-definitions-20261015-1.pom
- Country/Region: https://maven.inf-ai.duckdns.org/releases/org/aksw/data/thirdparty/org/fao/faostat/geographic-definitions-20261015/1/geographic-definitions-20261015-1-country-region.csv.zst
- Country Group: https://maven.inf-ai.duckdns.org/releases/org/aksw/data/thirdparty/org/fao/faostat/geographic-definitions-20261015/1/geographic-definitions-20261015-1-country-group-membership.csv.zst
- Provenance: https://maven.inf-ai.duckdns.org/releases/org/aksw/data/thirdparty/org/fao/faostat/geographic-definitions-20261015/1/geographic-definitions-20261015-1-provenance.json
- Source README: https://maven.inf-ai.duckdns.org/releases/org/aksw/data/thirdparty/org/fao/faostat/geographic-definitions-20261015/1/geographic-definitions-20261015-1-readme.md
- The fetch service caches the two CSV.zst files and their provenance/README in
  `data/`. The compressed files decompress byte-for-byte to the original CSVs.
  The attached provenance uses the original uncompressed filenames and hashes.

## Content identity

| Input | Compressed SHA-256 | Original CSV SHA-256 |
| --- | --- | --- |
| `country-region.csv.zst` | `ce70441854b36ea1db7f28f9363461056752543e0d869bd4416c6c29fef5a26f` | `0c059ca0db4043a1ea56a2abba658cceada715119a100567af43f4ec41023ae1` |
| `country-group-membership.csv.zst` | `71f4acec21562f228b58344d77aa469813a14e4bc86c45f51c5fa4cde6c50abe` | `8e8519e7f966687149044ac93a54a1766def4b9dab3f08745f5ca6ba1ce9ed0a` |

## Derivation

`ontop/load.sql` retains all 374 concordance rows in
`faostat_country_definition` and all 2,551 membership rows (55 groups) in
`faostat_area_membership`. Column identifiers and M49 values remain strings;
validity years are nullable integers. Primary keys reject duplicate source
codes/pairs; conflicting member/concordance ISO3 values fail the transaction.

Eligible country rows have a three-uppercase-letter source ISO3, no source end
year, and are not group identifiers. Four explicit exceptions are excluded:

| FAOSTAT code | Source identifier | Reason |
| --- | --- | --- |
| 259 | CHA | Channel Islands is a statistical grouping, not an ISO alpha-3 country identity. |
| 111 | JTN | Obsolete Johnston Island identifier. |
| 139 | MID | Obsolete Midway Island identifier. |
| 242 | WAK | Obsolete Wake Island identifier. |

These four source entries have no end year. Cross-check reference: the official
UNSD country/area and ISO-alpha3 table at
https://unstats.un.org/unsd/methodology/m49/overview/ (checked 2026-10-15).
It lists Guernsey and Jersey separately, and the United States Minor Outlying
Islands as UMI. No sovereign-state replacement or successor link is inferred.
TWN is retained from FAO's concordance as a separate statistical economy, as
with TiVA. This policy is not a generic test of every ISO-like identifier.

`faostat_country` contains the eligible concordance. `faostat_area_country`
contains distinct `(AREA_CODE, COUNTRY_CODE)` pairs for areas in the QCL fact
code list: single-country links plus eligible source-listed group members.
The current membership export is flat; no inferred nesting is added. Country
members need not themselves have QCL observations. Area concepts remain scoped
to QCL (including null-value source rows).

The R2RML predicate is `https://example.org/faostat/vocab/hasCountry`; objects
use the same `https://example.org/country/{ISO3}` IRIs as TiVA. No descriptive
triples are emitted for the country resources.

## Omissions and temporal meaning

A historical area's old three-letter code is not a current country identity.
Explicitly ended rows are excluded, including SCG and ANT. FAO-specific codes
such as F15 and F351 are excluded rather than treated as ISO3 codes. China's
aggregate (351) has no explicit membership in the export; it receives no
invented expansion or CHN identity link. Mainland China (41), Hong Kong (96),
Macao (128) and Taiwan (214) retain their separate source identities.

Inspect `faostat_area_country_unresolved` for QCL areas with no eligible links,
and `faostat_area_member_exclusion` for source memberships omitted from the
QCL country links. Raw definitions retain every excluded row.

Group membership is the source's retrieved classification, filtered as above;
it is not observation-year-specific. For example, EU27 has 30 source member
rows, including three historical areas, and yields 27 eligible country links.
Do not infer historical membership from an observation's year. These lists do
not certify a 2025 classification simply because the fact snapshot is 2025.
Membership joins support discovery, not allocation or summation of aggregate
values: a regional observation repeated per country would overcount.
