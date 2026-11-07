# HOW TO RUN (Isolation Tests)

1. Initialize schema and data

```
mysql -u root < sakila-schema.sql
mysql -u root < sakila-data.sql
```

2. open the sql files, edit the isolation type (as needed) on both files (ensure they BOTH have the same type). example below is serializable isolation

```
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE; -- CHANGE ISOLATION TYPE
```

3. run the A script first (with -t flag to format it as table)

```
mysql -t -u root sakila < dirtyread_A.sql
```

4. run the B script in another terminal within 10 seconds of running the A script

```
mysql -t -u root sakila < dirtyread_B.sql
```

Another way to run it is to use the automated experiment script:

```bash
uv run run_experiments.py
```
