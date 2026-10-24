-- Rebuild facts, derived lookup columns, code lists and indexes atomically.
BEGIN TRANSACTION;

CREATE OR REPLACE TABLE faostat (
    AREA_CODE INTEGER, M49_CODE VARCHAR, AREA VARCHAR,
    ITEM_CODE INTEGER, CPC_CODE VARCHAR, ITEM VARCHAR,
    ELEMENT_CODE INTEGER, ELEMENT VARCHAR, YEAR_CODE INTEGER, YEAR INTEGER,
    UNIT VARCHAR, OBS_VALUE DOUBLE, FLAG VARCHAR, NOTE VARCHAR,
    AREA_CODE_LEXICAL VARCHAR, ITEM_CODE_LEXICAL VARCHAR,
    ELEMENT_CODE_LEXICAL VARCHAR, YEAR_LEXICAL VARCHAR,
    OBSERVATION_LOCAL_NAME VARCHAR, OBS_VALUE_LEXICAL VARCHAR
);
INSERT INTO faostat
WITH typed AS (
    SELECT CAST("Area Code" AS INTEGER) AS AREA_CODE,
           replace("Area Code (M49)", chr(39), '') AS M49_CODE, "Area" AS AREA,
           CAST("Item Code" AS INTEGER) AS ITEM_CODE,
           replace("Item Code (CPC)", chr(39), '') AS CPC_CODE, "Item" AS ITEM,
           CAST("Element Code" AS INTEGER) AS ELEMENT_CODE, "Element" AS ELEMENT,
           CAST("Year Code" AS INTEGER) AS YEAR_CODE, CAST("Year" AS INTEGER) AS YEAR,
           "Unit" AS UNIT, CAST("Value" AS DOUBLE) AS OBS_VALUE,
           "Flag" AS FLAG, "Note" AS NOTE
    FROM read_csv('/data/FAOSTAT.csv.zst', header=true, all_varchar=true)
), lexical AS (
    SELECT *, CAST(AREA_CODE AS VARCHAR) AS AREA_CODE_LEXICAL,
           CAST(ITEM_CODE AS VARCHAR) AS ITEM_CODE_LEXICAL,
           CAST(ELEMENT_CODE AS VARCHAR) AS ELEMENT_CODE_LEXICAL,
           CAST(YEAR AS VARCHAR) AS YEAR_LEXICAL
    FROM typed
)
SELECT *,
       -- Integer components contain no separator hyphens except a possible
       -- leading minus. Escape that minus to keep the encoding reversible.
       CASE WHEN OBS_VALUE IS NOT NULL AND AREA_CODE IS NOT NULL
                 AND ITEM_CODE IS NOT NULL AND ELEMENT_CODE IS NOT NULL AND YEAR IS NOT NULL
            THEN replace(AREA_CODE_LEXICAL, '-', '~2D') || '-'
              || replace(ITEM_CODE_LEXICAL, '-', '~2D') || '-'
              || replace(ELEMENT_CODE_LEXICAL, '-', '~2D') || '-'
              || replace(YEAR_LEXICAL, '-', '~2D')
       END AS OBSERVATION_LOCAL_NAME,
       CAST(OBS_VALUE AS VARCHAR) AS OBS_VALUE_LEXICAL
FROM lexical;

-- Deduplicate complete code-list rows once. Conflicting labels/codes for one
-- key fail the primary key rather than silently choosing a label.
-- Include rows with null observation values, as the original mappings did.
CREATE OR REPLACE TABLE faostat_area (AREA_CODE VARCHAR PRIMARY KEY, AREA VARCHAR, M49_CODE VARCHAR);
INSERT INTO faostat_area SELECT DISTINCT AREA_CODE_LEXICAL, AREA, M49_CODE FROM faostat WHERE AREA_CODE IS NOT NULL;
-- Preserve the official 20261015 definitions as strings, including leading
-- zero M49 codes and source-specific ISO-like aggregate identifiers.
CREATE OR REPLACE TABLE faostat_country_definition (
    AREA_CODE VARCHAR PRIMARY KEY, AREA VARCHAR NOT NULL, M49_CODE VARCHAR,
    ISO2_CODE VARCHAR, ISO3_CODE VARCHAR, START_YEAR INTEGER, END_YEAR INTEGER
);
INSERT INTO faostat_country_definition
SELECT "Country Code", "Country", "M49 Code", "ISO2 Code", "ISO3 Code",
       CAST("Start Year" AS INTEGER), CAST("End Year" AS INTEGER)
FROM read_csv('/data/country-region.csv.zst', header=true, all_varchar=true);

CREATE OR REPLACE TABLE faostat_area_membership (
    AREA_CODE VARCHAR, AREA VARCHAR NOT NULL, GROUP_M49_CODE VARCHAR,
    MEMBER_CODE VARCHAR, MEMBER_AREA VARCHAR NOT NULL, M49_CODE VARCHAR,
    ISO2_CODE VARCHAR, ISO3_CODE VARCHAR,
    PRIMARY KEY (AREA_CODE, MEMBER_CODE)
);
INSERT INTO faostat_area_membership
SELECT "Country Group Code", "Country Group", "Group M49 Code",
       "Country Code", "Country", "M49 Code", "ISO2 Code", "ISO3 Code"
FROM read_csv('/data/country-group-membership.csv.zst', header=true, all_varchar=true);

-- Reject inconsistent ISO3 concordances rather than choosing one silently.
SELECT CASE WHEN count(*) = 0 THEN true ELSE error('Conflicting geographic ISO3 definitions') END
FROM faostat_area_membership m JOIN faostat_country_definition c ON m.MEMBER_CODE = c.AREA_CODE
WHERE m.ISO3_CODE IS DISTINCT FROM c.ISO3_CODE;

-- Source definitions with no end year and a three-letter alphabetic ISO3.
-- Four source entries still have obsolete/non-ISO identifiers despite missing
-- end years: CHA (Channel Islands), JTN, MID, WAK. Do not mint countries for
-- them. TWN is retained as a separately coded statistical economy, as in TiVA.
-- Policy and source references: faostat-geographic-definitions.meta.md.
CREATE OR REPLACE TABLE faostat_country (
    AREA_CODE VARCHAR PRIMARY KEY, COUNTRY_CODE VARCHAR NOT NULL UNIQUE
);
INSERT INTO faostat_country
SELECT c.AREA_CODE, c.ISO3_CODE FROM faostat_country_definition c
WHERE regexp_full_match(c.ISO3_CODE, '[A-Z]{3}') AND c.END_YEAR IS NULL
  AND c.AREA_CODE NOT IN ('259', '111', '139', '242')
  AND NOT EXISTS (SELECT 1 FROM faostat_area_membership m WHERE m.AREA_CODE = c.AREA_CODE);

-- Memberships in this source are already flat. A geographic area receives
-- its verified single-country link or its source-listed eligible members.
-- Keep dataset area concepts scoped to the fact table (including null values).
CREATE OR REPLACE TABLE faostat_area_country (
    AREA_CODE VARCHAR, COUNTRY_CODE VARCHAR,
    PRIMARY KEY (AREA_CODE, COUNTRY_CODE)
);
INSERT INTO faostat_area_country
SELECT a.AREA_CODE, c.COUNTRY_CODE
FROM faostat_area a JOIN faostat_country c ON a.AREA_CODE = c.AREA_CODE
UNION
SELECT a.AREA_CODE, c.COUNTRY_CODE
FROM faostat_area a JOIN faostat_area_membership m ON a.AREA_CODE = m.AREA_CODE
JOIN faostat_country c ON m.MEMBER_CODE = c.AREA_CODE;
CREATE INDEX faostat_area_country_country_code_idx ON faostat_area_country (COUNTRY_CODE);

-- Keep omissions inspectable in SQL instead of inventing successor-country,
-- sovereign-state or China-aggregate expansions.
CREATE OR REPLACE TABLE faostat_area_country_unresolved AS
SELECT a.AREA_CODE, a.AREA,
       CASE WHEN c.AREA_CODE IS NULL THEN 'missing_definition'
            WHEN c.END_YEAR IS NOT NULL THEN 'historical_area'
            ELSE 'no_eligible_country_or_membership' END AS REASON
FROM faostat_area a LEFT JOIN faostat_country_definition c ON a.AREA_CODE = c.AREA_CODE
WHERE NOT EXISTS (SELECT 1 FROM faostat_area_country ac WHERE ac.AREA_CODE = a.AREA_CODE);
CREATE OR REPLACE TABLE faostat_area_member_exclusion AS
SELECT m.AREA_CODE, m.MEMBER_CODE, m.MEMBER_AREA, m.ISO3_CODE,
       CASE WHEN c.AREA_CODE IS NULL THEN 'missing_definition'
            WHEN c.END_YEAR IS NOT NULL THEN 'historical_area'
            ELSE 'non_country_identifier' END AS REASON
FROM faostat_area_membership m JOIN faostat_area a ON a.AREA_CODE = m.AREA_CODE
LEFT JOIN faostat_country_definition c ON c.AREA_CODE = m.MEMBER_CODE
WHERE NOT EXISTS (SELECT 1 FROM faostat_country eligible WHERE eligible.AREA_CODE = m.MEMBER_CODE);

CREATE OR REPLACE TABLE faostat_item (ITEM_CODE VARCHAR PRIMARY KEY, ITEM VARCHAR, CPC_CODE VARCHAR);
INSERT INTO faostat_item SELECT DISTINCT ITEM_CODE_LEXICAL, ITEM, CPC_CODE FROM faostat WHERE ITEM_CODE IS NOT NULL;
CREATE OR REPLACE TABLE faostat_element (ELEMENT_CODE VARCHAR PRIMARY KEY, ELEMENT VARCHAR);
INSERT INTO faostat_element SELECT DISTINCT ELEMENT_CODE_LEXICAL, ELEMENT FROM faostat WHERE ELEMENT_CODE IS NOT NULL;
CREATE OR REPLACE TABLE faostat_unit (UNIT VARCHAR PRIMARY KEY);
INSERT INTO faostat_unit SELECT DISTINCT UNIT FROM faostat WHERE UNIT IS NOT NULL;
CREATE OR REPLACE TABLE faostat_flag (FLAG VARCHAR PRIMARY KEY);
INSERT INTO faostat_flag SELECT DISTINCT FLAG FROM faostat WHERE FLAG IS NOT NULL;

-- Enforce the original declared fact key and the mapped observation key.
-- The composite index is for integrity; selective lookups use single columns.
CREATE UNIQUE INDEX faostat_key_idx ON faostat (AREA_CODE, ITEM_CODE, ELEMENT_CODE, YEAR);
CREATE UNIQUE INDEX faostat_observation_local_name_idx ON faostat (OBSERVATION_LOCAL_NAME);
CREATE INDEX faostat_area_code_lexical_idx ON faostat (AREA_CODE_LEXICAL);
CREATE INDEX faostat_item_code_lexical_idx ON faostat (ITEM_CODE_LEXICAL);
CREATE INDEX faostat_element_code_lexical_idx ON faostat (ELEMENT_CODE_LEXICAL);
CREATE INDEX faostat_year_lexical_idx ON faostat (YEAR_LEXICAL);
CREATE INDEX faostat_obs_value_lexical_idx ON faostat (OBS_VALUE_LEXICAL);
CREATE INDEX faostat_unit_idx ON faostat (UNIT);
CREATE INDEX faostat_flag_idx ON faostat (FLAG);
CREATE INDEX faostat_note_idx ON faostat (NOTE);
ANALYZE;
COMMIT;
