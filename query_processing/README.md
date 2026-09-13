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

## Declaration of Generative AI Use

During the conduct of this hands-on activity, we used Claude Opus 5 to assist with the following tasks:

- Setting up Docker.

---

Statement of Accountability. By submitting this report, we explicitly affirm the following:

- We accept full accountability for the accuracy and integrity of all content in our written and oral reports.
- We have examined and validated all AI-assisted contributions included in our written and oral reports.
- We acknowledge the inherent limitations of GenAI systems, including the potential for technical errors, factual inaccuracies, hallucinations, or biases.
- We fully comprehend the AI-generated outputs used in our written and oral reports. We understand that the inability to explain these concepts in our own words during evaluations will be treated as a violation of academic integrity, and we accept the consequences of any such misuse.
