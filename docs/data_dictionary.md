# Data dictionary

The authoritative field-level dictionary is [`data_dictionary.csv`](data_dictionary.csv). It lists every column in [`schema.sql`](schema.sql), including type, requiredness, allowed values, units, uniqueness, and validation rules.

## Cardinality

Customers have many orders, order lines through orders, engagement events, support cases, consent records, memberships, and action outcomes. Products have many order lines. Orders have many lines and returns reference their originating sale. Segment rules and actions connect to customers through memberships and outcomes; eligibility is resolved by `ActionEligibilityBridge`.

## Lifecycle diagrams

Customer lifecycle: `NEW -> ACTIVE -> DORMANT -> CHURNED`; any state may transition to `SUPPRESSED` when marketing consent is unavailable. Consent lifecycle: `GRANTED -> WITHDRAWN`, represented as append-only rows with effective dates. Support lifecycle: `OPEN -> IN_PROGRESS -> RESOLVED -> CLOSED`; `REOPENED` may return to `IN_PROGRESS`. Segment membership lifecycle: `ENTER -> ACTIVE -> EXIT`.

## Conventions

Dates and timestamps are ISO-8601 text in the schema so the DDL is compatible with both SQLite and PostgreSQL loading workflows. Amounts use one configured currency. No raw personal information is generated; email values are synthetic tokens.
