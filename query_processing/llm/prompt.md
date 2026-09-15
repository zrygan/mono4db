<role>
You are a senior database engineer and Python software engineer. You write production-quality, deterministic data generation scripts.
</role>

<task>
Write a standalone Python 3 script named `make_dump.py` that generates realistic synthetic data for the Sakila-derived PostgreSQL schema below, and writes it to a file named `dump.sql`.

The script must run with no external dependencies (standard library only) and must produce an identical `dump.sql` on every run (seeded, deterministic).
</task>

<schema>
The target database has exactly these 10 tables. Do not add, remove, or rename columns.

```sql
CREATE TABLE language (
    language_id SERIAL PRIMARY KEY,
    name CHAR(20) NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE category (
    category_id SERIAL PRIMARY KEY,
    name VARCHAR(25) NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE actor (
    actor_id SERIAL PRIMARY KEY,
    first_name VARCHAR(45) NOT NULL,
    last_name VARCHAR(45) NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE film (
    film_id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    release_year INTEGER,
    language_id INTEGER NOT NULL REFERENCES language(language_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    original_language_id INTEGER REFERENCES language(language_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    rental_duration SMALLINT NOT NULL DEFAULT 3,
    rental_rate NUMERIC(4,2) NOT NULL DEFAULT 4.99,
    length SMALLINT,
    replacement_cost NUMERIC(5,2) NOT NULL DEFAULT 19.99,
    rating VARCHAR(10) DEFAULT 'G',
    special_features TEXT,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE film_actor (
    actor_id INTEGER NOT NULL REFERENCES actor(actor_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    film_id INTEGER NOT NULL REFERENCES film(film_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (actor_id, film_id)
);

CREATE TABLE film_category (
    film_id INTEGER NOT NULL REFERENCES film(film_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    category_id INTEGER NOT NULL REFERENCES category(category_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (film_id, category_id)
);

CREATE TABLE store (
    store_id SERIAL PRIMARY KEY,
    store_name VARCHAR(50) NOT NULL,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE customer (
    customer_id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES store(store_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    first_name VARCHAR(45) NOT NULL,
    last_name VARCHAR(45) NOT NULL,
    email VARCHAR(50),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    create_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory (
    inventory_id SERIAL PRIMARY KEY,
    film_id INTEGER NOT NULL REFERENCES film(film_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    store_id INTEGER NOT NULL REFERENCES store(store_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rental (
    rental_id SERIAL PRIMARY KEY,
    rental_date TIMESTAMP NOT NULL,
    inventory_id INTEGER NOT NULL REFERENCES inventory(inventory_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    customer_id INTEGER NOT NULL REFERENCES customer(customer_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    return_date TIMESTAMP,
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

</schema>

<generation_order>
Generate and write data in this exact dependency order, since later tables reference earlier ones by foreign key:

1. language
2. category
3. store
4. actor
5. film
6. film_category
7. film_actor
8. customer
9. inventory
10. rental
</generation_order>

<row_counts>

| Table | Rows | Notes |
| --- | --- | --- |
| language | 6 | English, Spanish, French, German, Italian, Japanese |
| category | 16 | Standard movie genres |
| store | 2 | "Flagship" and "Suburban" |
| actor | 1,500 | |
| film | 5,000 | |
| film_category | 5,000 | one row per film |
| film_actor | ~15,000 | 2–5 actors per film |
| customer | 10,000 | |
| inventory | 50,000 | |
| rental | 500,000 | |
</row_counts>

<realism_requirements>
Do not use uniform random distributions. Implement each of the following explicitly:

1. **Actor/film popularity (Zipfian).** Implement inverse transform sampling for a Zipf/power-law distribution with alpha ≈ 1.25. Use it so that a small tier of "superstar" actors appears in disproportionately many films, and a small tier of popular films accounts for most inventory copies and rental volume. A pure Zipf law at this alpha is too extreme to be plausible at these table sizes (e.g. one actor in ~60% of all films) — use a Zipf-Mandelbrot rank offset, or another damping approach, to flatten the head of the distribution while preserving the power-law tail. Choose offsets/parameters so that, roughly: the top actor appears in the low hundreds of films (not thousands), and the top film accounts for a few hundred inventory copies (not many thousands).

2. **Temporal seasonality.** Rentals span 2024-01-01 through 2025-12-31. Apply monthly weighting so June/July and December have noticeably higher rental volume than other months (simulate summer-blockbuster and holiday surges).

3. **Store imbalance.** Store 1 gets ~60% of inventory rows and ~60% of rental volume; Store 2 gets ~40% of both.

4. **Customer frequency (Pareto).** A minority of "power renter" customers should generate a disproportionate share of the 500,000 rentals; most customers rent infrequently. An untruncated Pareto draw at a plausible alpha can produce a single customer with tens of thousands of rentals over a two-year window, which is not realistic — truncate or cap the draw so no customer's rental count is implausible for the time span.

5. **Return dates.** `return_date` = `rental_date + rental_duration days`, with random jitter (e.g., ± a few days). Leave `return_date` NULL for ~3% of rentals to represent currently-unreturned rentals. Additionally: a single inventory copy cannot be rented out to a second customer before its prior loan's `return_date` — resolve or prevent overlapping loans of the same inventory_id, and make sure NULL (unreturned) return dates are only assigned to a copy's most recent loan, not one with a later loan already generated after it.
</realism_requirements>

<technical_requirements>

- **Referential integrity:** every foreign key must reference a row that was already generated in an earlier step. No orphaned keys.
- **Output format:** use `COPY table (col1, col2, ...) FROM stdin;` blocks terminated with `\.`, not `INSERT` statements — this is a bulk-load performance requirement.
- **Sequences:** after all COPY blocks, emit `SELECT setval('<table>_<col>_seq', MAX(<col>))` (or equivalent) for every SERIAL column, so the sequence counters match the highest inserted ID.
- **Determinism:** call `random.seed(42)` once at the start of the script. Two runs must produce byte-identical `dump.sql` files.
- **Dependencies:** standard library only (`random`, `math`, `datetime`, `pathlib`, etc.). No `faker`, `numpy`, or `psycopg2`.
- **Escaping:** properly escape any characters in generated text (e.g., tabs, newlines, backslashes) that would break `COPY ... FROM stdin` formatting. Note: in PostgreSQL's COPY TEXT format, single quotes have no special meaning and must NOT be escaped or doubled — only backslash, tab, newline, carriage return, and NULL (as `\N`) require handling.
</technical_requirements>

<output_format>
Return:

1. The complete contents of `make_dump.py` in a single code block.
2. A short (3–6 line) explanation of how the Zipfian sampling function works, including how the rank-offset/damping approach works.
3. Any assumptions you made that weren't fully specified above (e.g., exact email format, exact rating value set, exact special_features vocabulary, film length range, exact damping/cap parameters chosen for the Zipf and Pareto distributions).

Do not include commentary about the task itself — only the script, the brief explanation, and the assumptions list.
</output_format>
