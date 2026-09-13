# Query Processing

Query processing and optimization analysis project.

## Quick Start

Set up container:

```bash
sudo docker compose up -d postgres
```

Then run the project:

```bash
docker compose run --rm query_processing
```

## CLI Options

```bash
# Run with defaults (refreshes DB from dump.sql, runs all queries)
sudo docker compose run --rm query_processing

# Run a specific query folder
sudo docker compose run --rm query_processing python src/main.py --query query1

# Custom iterations and warmup runs
sudo docker compose run --rm query_processing python src/main.py --iterations 5 --warmup 2
```

> Why **warmup** and **iterations**?
>
> Sometimes, other ongoing processes add to the load of the CPU (for instance, the warmping up of the JVM JIT compiler). So, we can define some long enough warmup *n* to ignore the first *n* calls of the query which may or may not have been affected by other processes warming up. This is the same idea for using *m* iternations.
