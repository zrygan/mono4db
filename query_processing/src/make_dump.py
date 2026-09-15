#!/usr/bin/env python3
"""
generate_dump.py
================

Deterministic synthetic-data generator for a Sakila-derived PostgreSQL schema.

Writes a single file, ``dump.sql``, containing PostgreSQL ``COPY ... FROM stdin``
blocks in foreign-key dependency order, followed by ``setval()`` calls that
re-align every SERIAL sequence with the highest inserted id.

Standard library only. Two runs produce byte-identical output.

Usage:
    python3 query_processing/src/generate_dump.py query_processing/sql/dump.sql
"""

from __future__ import annotations

import bisect
import calendar
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEED = 42
DEFAULT_OUTPUT = Path("dump.sql")

N_ACTORS = 1_500
N_FILMS = 5_000
N_CUSTOMERS = 10_000
N_INVENTORY = 50_000
N_RENTALS = 500_000

ZIPF_ALPHA = 1.25          # actor / film popularity exponent

# Zipf-Mandelbrot rank offsets.  A pure Zipf (offset 0) at alpha=1.25 puts ~22%
# of all probability mass on rank 1 alone, which would put one actor in 3 of
# every 5 films and stack 12,000 copies of a single title.  A rank offset keeps
# the alpha=1.25 tail while flattening the head into a believable "superstar"
# tier.  See zipf_cdf() for the formula.
ZIPF_OFFSET_ACTOR = 30     # -> top actor in ~200 of 5,000 films
ZIPF_OFFSET_FILM = 60      # -> top title ~300 inventory copies
ZIPF_OFFSET_COPY = 2000    # -> per-copy turnover premium for hot titles

PARETO_ALPHA = 1.16        # customer rental frequency (80/20-style tail)
PARETO_CAP = 60.0          # truncate the Pareto tail (see assumptions)
STORE_1_SHARE = 0.60       # share of inventory rows and rental volume

UNRETURNED_FRACTION = 0.03  # share of rentals left with NULL return_date

RENTAL_WINDOW_START = datetime(2024, 1, 1)
RENTAL_WINDOW_END = datetime(2025, 12, 31)

# Static "seed" timestamps so the reference tables are stable and deterministic.
EPOCH_STATIC = datetime(2023, 1, 1, 9, 0, 0)
CATALOGUE_WINDOW = (datetime(2023, 1, 1), datetime(2023, 12, 31))
CUSTOMER_SIGNUP_WINDOW = (datetime(2022, 1, 1), datetime(2023, 12, 31))

# Monthly demand multipliers: summer blockbuster surge (Jun/Jul) and a
# December holiday surge, with a soft shoulder in Aug/Nov.
MONTH_WEIGHTS = {
    1: 0.85, 2: 0.80, 3: 0.90, 4: 0.95, 5: 1.05, 6: 1.75,
    7: 1.85, 8: 1.20, 9: 0.90, 10: 0.95, 11: 1.10, 12: 1.70,
}
YEAR_WEIGHTS = {2024: 1.00, 2025: 1.12}  # modest year-over-year growth

# Rentals cluster in late afternoon / evening.
HOUR_WEIGHTS = [
    0.15, 0.08, 0.05, 0.04, 0.04, 0.06, 0.15, 0.35, 0.60, 0.75, 0.85, 0.95,
    1.05, 1.10, 1.20, 1.45, 1.85, 2.20, 2.40, 2.25, 1.80, 1.30, 0.80, 0.40,
]

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

LANGUAGES = ["English", "Spanish", "French", "German", "Italian", "Japanese"]
LANGUAGE_WEIGHTS = [0.74, 0.07, 0.06, 0.05, 0.04, 0.04]

CATEGORIES = [
    "Action", "Animation", "Children", "Classics", "Comedy", "Documentary",
    "Drama", "Family", "Foreign", "Games", "Horror", "Music", "New",
    "Sci-Fi", "Sports", "Travel",
]
CATEGORY_WEIGHTS = [
    1.60, 0.85, 0.80, 0.55, 1.50, 0.60, 1.55, 0.75, 0.50, 0.35, 1.05, 0.55,
    0.90, 1.20, 0.60, 0.40,
]

STORES = ["Flagship", "Suburban"]

FIRST_NAMES = [
    "Aaliyah", "Adam", "Adrian", "Aisha", "Alan", "Alba", "Alejandro", "Alice",
    "Amara", "Amelia", "Andre", "Andrea", "Angela", "Anita", "Anton", "Arjun",
    "Arthur", "Astrid", "Aubrey", "Audrey", "Beatriz", "Ben", "Bianca", "Blake",
    "Bruno", "Camila", "Carl", "Carmen", "Caroline", "Cedric", "Celia", "Cesar",
    "Charlotte", "Chen", "Chloe", "Clara", "Colin", "Cora", "Damien", "Daniela",
    "Dario", "David", "Delia", "Denise", "Diego", "Dimitri", "Dorothy", "Duncan",
    "Edith", "Eduardo", "Elena", "Eli", "Elsie", "Emeka", "Emil", "Emma",
    "Enzo", "Esther", "Ethan", "Eva", "Fabian", "Faith", "Farid", "Felicity",
    "Fiona", "Florence", "Franco", "Freya", "Gabriel", "Gemma", "Gerald",
    "Gina", "Grace", "Gregor", "Guilherme", "Hana", "Harold", "Hassan",
    "Heather", "Hector", "Helena", "Hiro", "Hugo", "Ibrahim", "Ida", "Igor",
    "Imani", "Ines", "Irene", "Isaac", "Ivan", "Jade", "Jasper", "Javier",
    "Jean", "Jelena", "Jerome", "Joan", "Jonas", "Josefina", "Judith", "Julius",
    "Kai", "Kamil", "Karin", "Kasia", "Keiko", "Kenji", "Khalid", "Kiran",
    "Klaus", "Lachlan", "Laila", "Lars", "Laura", "Leandro", "Leila", "Leo",
    "Lila", "Linus", "Lorena", "Lucas", "Lucia", "Ludmila", "Lukas", "Mabel",
    "Magnus", "Maia", "Malik", "Manon", "Marcel", "Margot", "Mariana", "Mario",
    "Martha", "Mateo", "Matilda", "Maya", "Mei", "Melina", "Miguel", "Mira",
    "Miriam", "Mohan", "Nadia", "Naomi", "Natalia", "Nathan", "Neve", "Niamh",
    "Nikolai", "Nina", "Noah", "Nora", "Octavia", "Olga", "Oliver", "Omar",
    "Oscar", "Paloma", "Pascal", "Patricia", "Paulo", "Petra", "Philip",
    "Priya", "Quentin", "Rafael", "Ramona", "Raul", "Rebecca", "Reza",
    "Rhiannon", "Ricardo", "Rita", "Roman", "Rosa", "Rowan", "Ruby", "Rupert",
    "Sadie", "Salma", "Samir", "Sandra", "Sasha", "Sebastian", "Selma",
    "Sergio", "Shaun", "Sienna", "Sofia", "Soren", "Stella", "Sven", "Sylvia",
    "Tadeusz", "Tamara", "Tariq", "Tessa", "Thea", "Theodore", "Tomas",
    "Ursula", "Valeria", "Vera", "Victor", "Vincent", "Viola", "Walter",
    "Wanda", "Wei", "Wesley", "Willa", "Xavier", "Yara", "Yasmin", "Yuki",
    "Yusuf", "Zainab", "Zara", "Zoe",
]

LAST_NAMES = [
    "Abbott", "Acosta", "Adeyemi", "Aguilar", "Ahmed", "Akande", "Albrecht",
    "Alonso", "Andersen", "Andrade", "Arnaud", "Ashford", "Azevedo", "Baptiste",
    "Barnes", "Bauer", "Beaumont", "Belanger", "Bennett", "Bergstrom",
    "Bianchi", "Blackwood", "Bonnet", "Borges", "Bouchard", "Bradshaw",
    "Brennan", "Brossard", "Bukowski", "Caldwell", "Campos", "Caruso",
    "Castellanos", "Chandra", "Chatterjee", "Chevalier", "Chowdhury",
    "Christensen", "Clarke", "Coelho", "Conti", "Cortez", "Costa", "Cruz",
    "D'Alessandro", "D'Angelo", "Dalgaard", "Danilov", "Darwish", "Da Silva",
    "Delacroix", "Delgado", "Demir", "Dimitrov", "Donnelly", "Dubois",
    "Duarte", "Eberhardt", "Egan", "Eklund", "Ellison", "Engel", "Escobar",
    "Fairbanks", "Falcone", "Farrell", "Ferreira", "Fitzgerald", "Fontaine",
    "Forsberg", "Fournier", "Gallagher", "Garcia", "Gauthier", "Gerasimov",
    "Gilmore", "Giordano", "Gonzalez", "Grant", "Greco", "Gruber",
    "Gustafsson", "Halvorsen", "Hamilton", "Hanaoka", "Hansen", "Haugen",
    "Hayashi", "Hendricks", "Herrera", "Hoffmann", "Holloway", "Horvath",
    "Huang", "Ibarra", "Iglesias", "Ingram", "Ishikawa", "Jankowski",
    "Jensen", "Jimenez", "Kaczmarek", "Kalinin", "Kamara", "Kaufman",
    "Kavanagh", "Keller", "Kimura", "Kirkland", "Klein", "Kovacs", "Kowalski",
    "Krause", "Lacroix", "Lambert", "Langdon", "Larsen", "Laurent", "Leclerc",
    "Lindqvist", "Lombardi", "Lopez", "Lovelace", "Lundgren", "Maartens",
    "Machado", "Maddox", "Magnusson", "Mahmoud", "Marchetti", "Marino",
    "Martinez", "Mathieu", "Mbeki", "McAllister", "McKenna", "Medeiros",
    "Mendoza", "Meyer", "Mikkelsen", "Moreau", "Moreno", "Morrissey",
    "Mostafa", "Mueller", "Nakamura", "Navarro", "Nguyen", "Nicolescu",
    "Nielsen", "Novak", "Nowak", "O'Brien", "O'Donnell", "Okafor", "Oliveira",
    "Olsen", "Ortega", "Ostrowski", "Paczkowski", "Palmer", "Pappas",
    "Pedersen", "Pereira", "Petrov", "Pham", "Pinto", "Popescu", "Prescott",
    "Quintana", "Radcliffe", "Rahman", "Ramirez", "Rasmussen", "Redmond",
    "Reyes", "Ricci", "Richter", "Rinaldi", "Rivera", "Rocha", "Rodriguez",
    "Rosales", "Rossi", "Rousseau", "Sandoval", "Santoro", "Sawyer",
    "Schneider", "Schulz", "Serrano", "Sharma", "Shimizu", "Silva",
    "Sinclair", "Solberg", "Sorensen", "Sousa", "Stavros", "Steinberg",
    "Suzuki", "Svensson", "Szabo", "Tanaka", "Teixeira", "Thornton",
    "Tremblay", "Ueda", "Vance", "Varga", "Vasquez", "Velasquez", "Villanueva",
    "Vogel", "Wagner", "Wallace", "Watanabe", "Weber", "Whitfield",
    "Wojcik", "Yamamoto", "Yilmaz", "Zamora", "Zielinski",
]

TITLE_ADJECTIVES = [
    "Amber", "Ancient", "Atomic", "Blazing", "Brazen", "Broken", "Burning",
    "Crimson", "Crooked", "Crystal", "Dark", "Daring", "Distant", "Eternal",
    "Fearless", "Feral", "Final", "Forgotten", "Frozen", "Furious", "Gilded",
    "Golden", "Grand", "Hidden", "Hollow", "Infinite", "Iron", "Jagged",
    "Lonesome", "Lost", "Midnight", "Molten", "Nameless", "Northern",
    "Perfect", "Phantom", "Quiet", "Radiant", "Reckless", "Restless",
    "Sacred", "Savage", "Scarlet", "Secret", "Shattered", "Silent", "Silver",
    "Sleepless", "Solemn", "Southern", "Stolen", "Stubborn", "Sunken",
    "Tender", "Thundering", "Tragic", "Twilight", "Unbroken", "Velvet",
    "Wandering", "Wicked", "Wild", "Winter", "Wounded",
]

TITLE_NOUNS = [
    "Abyss", "Affair", "Anthem", "Apostle", "Archive", "Armada", "Ballad",
    "Bandit", "Banquet", "Beacon", "Bridge", "Cabaret", "Cannon", "Carnival",
    "Cathedral", "Cavalry", "Cipher", "Citadel", "Compass", "Confession",
    "Conspiracy", "Courier", "Covenant", "Crossing", "Crusade", "Dagger",
    "Detective", "Dominion", "Drifter", "Echo", "Eclipse", "Emissary",
    "Empire", "Escape", "Exodus", "Fable", "Falcon", "Fortress", "Foundry",
    "Frontier", "Gambit", "Gardener", "Garrison", "Gospel", "Harbour",
    "Harvest", "Highway", "Horizon", "Hourglass", "Hunter", "Inferno",
    "Inheritance", "Junction", "Kingdom", "Lantern", "Legacy", "Lighthouse",
    "Locket", "Machine", "Mariner", "Masquerade", "Menagerie", "Meridian",
    "Monsoon", "Mountain", "Mutiny", "Nomad", "Oath", "Obsession", "Odyssey",
    "Orchard", "Outpost", "Paradox", "Pilgrim", "Pioneer", "Prophecy",
    "Quarry", "Rebellion", "Reckoning", "Requiem", "Riddle", "Rodeo",
    "Sanctuary", "Sentinel", "Serenade", "Shadow", "Sonata", "Specter",
    "Stampede", "Stranger", "Summit", "Syndicate", "Tempest", "Testament",
    "Threshold", "Tribunal", "Tundra", "Vagabond", "Verdict", "Vigil",
    "Voyage", "Warden", "Whisper", "Wilderness", "Witness", "Zenith",
]

TITLE_PLACES = [
    "Alaska", "Andalusia", "Barcelona", "Berlin", "Bombay", "Brooklyn",
    "Cairo", "Casablanca", "Dakar", "Dublin", "Havana", "Helsinki",
    "Istanbul", "Kyoto", "Lisbon", "Marrakesh", "Montana", "Naples",
    "Odessa", "Patagonia", "Prague", "Reykjavik", "Saigon", "Santiago",
    "Seville", "Shanghai", "Siberia", "Tangier", "Valparaiso", "Vienna",
]

PLOT_SUBJECTS = [
    "a disgraced archivist", "a retired safecracker", "a small-town botanist",
    "a war correspondent", "a teenage chess prodigy", "an itinerant preacher",
    "a deep-sea welder", "a disillusioned prosecutor", "a travelling puppeteer",
    "a rookie air traffic controller", "a widowed lighthouse keeper",
    "a forger of Renaissance drawings", "a night-shift paramedic",
    "a cartographer with a failing memory", "an exiled concert pianist",
    "a cattle rancher's daughter", "a bankrupt theatre impresario",
    "a code-breaker on unpaid leave", "a beekeeper turned detective",
    "an understudy who never went on",
]

PLOT_COMPLICATIONS = [
    "must outrun a debt that was never theirs",
    "uncovers a ledger that should have burned",
    "is mistaken for a courier carrying stolen plates",
    "inherits a house with one locked room",
    "agrees to one last job for an old rival",
    "is called to testify against a former mentor",
    "discovers the town's water has been sold twice",
    "learns their sister has been alive for eleven years",
    "takes the blame for a fire they did not set",
    "finds a decade of unsent letters in a rented car",
    "is followed home by someone wearing their coat",
    "must smuggle a witness across two borders",
    "signs a contract written in a language they cannot read",
    "is offered an alibi by the only honest witness",
]

PLOT_SETTINGS = [
    "in a flooded mining town", "aboard a decommissioned ferry",
    "during a three-day power outage", "on the last night of the harvest fair",
    "in a monastery converted to a hotel", "along a closed mountain highway",
    "in the ruins of a seaside amusement park", "under martial curfew",
    "in a border town with two clocks", "at an airfield the maps no longer show",
    "through a winter that refuses to end", "in a city rebuilt on its own rubble",
]

SPECIAL_FEATURES = [
    "Trailers", "Commentaries", "Deleted Scenes", "Behind the Scenes",
]

RATINGS = ["G", "PG", "PG-13", "R", "NC-17"]
RATING_WEIGHTS = [0.09, 0.19, 0.30, 0.34, 0.08]

RENTAL_RATES = ["0.99", "2.99", "4.99"]
RENTAL_RATE_WEIGHTS = [0.30, 0.38, 0.32]

EMAIL_DOMAIN = "sakiladb.example.com"

# ---------------------------------------------------------------------------
# COPY-format helpers
# ---------------------------------------------------------------------------

# In PostgreSQL's COPY TEXT format the delimiter is a tab, rows are newline
# terminated, and backslash is the escape character.  Single quotes carry no
# special meaning here and must NOT be doubled -- doing so would corrupt the
# data.  \N is the NULL marker.
_COPY_ESCAPES = str.maketrans({
    "\\": "\\\\",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\v": "\\v",
    "\f": "\\f",
    "\b": "\\b",
})

NULL_MARKER = "\\N"


def fmt(value) -> str:
    """Render a Python value as one COPY TEXT field."""
    if value is None:
        return NULL_MARKER
    if value is True:
        return "t"
    if value is False:
        return "f"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, int):
        return str(value)
    return str(value).translate(_COPY_ESCAPES)


def row(*values) -> str:
    return "\t".join(fmt(v) for v in values) + "\n"


class DumpWriter:
    """Thin wrapper that emits COPY blocks and tracks sequence resets."""

    def __init__(self, handle):
        self.handle = handle
        self.sequences: list[tuple[str, str, int]] = []

    def raw(self, text: str) -> None:
        self.handle.write(text)

    def begin_copy(self, table: str, columns: list[str]) -> None:
        self.handle.write(
            "COPY {} ({}) FROM stdin;\n".format(table, ", ".join(columns))
        )

    def end_copy(self) -> None:
        self.handle.write("\\.\n\n")

    def note_sequence(self, table: str, column: str, max_id: int) -> None:
        self.sequences.append((table, column, max_id))

    def write_setvals(self) -> None:
        self.handle.write("-- Re-align SERIAL sequences with the loaded data.\n")
        for table, column, max_id in self.sequences:
            self.handle.write(
                "SELECT setval('{table}_{column}_seq', "
                "(SELECT MAX({column}) FROM {table}), true);\n".format(
                    table=table, column=column
                )
            )


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------


def build_cdf(weights: list[float]) -> list[float]:
    """Normalised cumulative distribution over ``weights``."""
    total = 0.0
    cdf: list[float] = []
    for w in weights:
        total += w
        cdf.append(total)
    cdf = [c / total for c in cdf]
    cdf[-1] = 1.0  # guard against float drift
    return cdf


def sample_cdf(cdf: list[float], rng: random.Random) -> int:
    """Inverse-transform sample: index of the first CDF entry >= U(0,1)."""
    return bisect.bisect_left(cdf, rng.random())


def zipf_cdf(n: int, alpha: float = ZIPF_ALPHA, offset: float = 0.0) -> list[float]:
    """CDF of a rank-ordered Zipf(-Mandelbrot) power law over ``n`` ranks.

    P(rank r) is proportional to 1 / (r + offset) ** alpha.  With offset=0 this
    is the textbook Zipf law; a positive offset damps the extreme head while
    leaving the power-law tail intact.
    """
    return build_cdf([1.0 / ((i + 1 + offset) ** alpha) for i in range(n)])


def pareto_weights(n: int, rng, alpha: float = PARETO_ALPHA,
                   x_min: float = 1.0, cap: float = PARETO_CAP) -> list[float]:
    """Draw ``n`` Pareto(alpha, x_min) weights by inverse transform.

    CDF F(x) = 1 - (x_min / x) ** alpha  =>  x = x_min * (1 - u) ** (-1/alpha)

    The draw is truncated at ``cap`` x_min: an untruncated Pareto occasionally
    produces a single weight thousands of times the mean, which here would mean
    one customer taking out ~50,000 rentals in two years.
    """
    return [min(cap, x_min * (1.0 - rng.random()) ** (-1.0 / alpha))
            for _ in range(n)]


def random_datetime(rng: random.Random, start: datetime, end: datetime) -> datetime:
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randrange(span))


# ---------------------------------------------------------------------------
# Table generators
# ---------------------------------------------------------------------------


def write_language(w: DumpWriter) -> list[int]:
    w.begin_copy("language", ["language_id", "name", "last_update"])
    ids = []
    for i, name in enumerate(LANGUAGES, start=1):
        ids.append(i)
        w.raw(row(i, name, EPOCH_STATIC))
    w.end_copy()
    w.note_sequence("language", "language_id", len(ids))
    return ids


def write_category(w: DumpWriter) -> list[int]:
    w.begin_copy("category", ["category_id", "name", "last_update"])
    ids = []
    for i, name in enumerate(CATEGORIES, start=1):
        ids.append(i)
        w.raw(row(i, name, EPOCH_STATIC))
    w.end_copy()
    w.note_sequence("category", "category_id", len(ids))
    return ids


def write_store(w: DumpWriter) -> list[int]:
    w.begin_copy("store", ["store_id", "store_name", "last_update"])
    ids = []
    for i, name in enumerate(STORES, start=1):
        ids.append(i)
        w.raw(row(i, name, EPOCH_STATIC))
    w.end_copy()
    w.note_sequence("store", "store_id", len(ids))
    return ids


def write_actor(w: DumpWriter, rng: random.Random) -> list[int]:
    w.begin_copy("actor", ["actor_id", "first_name", "last_name", "last_update"])
    ids = []
    for actor_id in range(1, N_ACTORS + 1):
        ids.append(actor_id)
        w.raw(row(
            actor_id,
            rng.choice(FIRST_NAMES),
            rng.choice(LAST_NAMES),
            random_datetime(rng, *CATALOGUE_WINDOW),
        ))
    w.end_copy()
    w.note_sequence("actor", "actor_id", N_ACTORS)
    return ids


def make_title(rng: random.Random, used: set) -> str:
    """Build a plausible, unique film title from the vocabularies."""
    for _ in range(40):
        pattern = rng.random()
        if pattern < 0.34:
            title = "{} {}".format(rng.choice(TITLE_ADJECTIVES), rng.choice(TITLE_NOUNS))
        elif pattern < 0.58:
            title = "The {} of {}".format(rng.choice(TITLE_NOUNS), rng.choice(TITLE_PLACES))
        elif pattern < 0.74:
            title = "The {} {}".format(rng.choice(TITLE_ADJECTIVES), rng.choice(TITLE_NOUNS))
        elif pattern < 0.87:
            title = "{} in {}".format(rng.choice(TITLE_NOUNS), rng.choice(TITLE_PLACES))
        else:
            title = "{} and {}".format(rng.choice(TITLE_NOUNS), rng.choice(TITLE_NOUNS))
        if title not in used:
            used.add(title)
            return title
    # Fall back to an explicit sequel suffix rather than looping forever.
    base = title
    n = 2
    while "{} {}".format(base, n) in used:
        n += 1
    title = "{} {}".format(base, n)
    used.add(title)
    return title


def make_description(rng: random.Random) -> str:
    return "A {} tale in which {} {} {}.".format(
        rng.choice(["riveting", "brooding", "wry", "tender", "bleak", "rousing",
                    "understated", "frantic", "meditative", "scabrous"]),
        rng.choice(PLOT_SUBJECTS),
        rng.choice(PLOT_COMPLICATIONS),
        rng.choice(PLOT_SETTINGS),
    )


def write_film(w: DumpWriter, rng: random.Random, language_ids: list[int]) -> dict:
    lang_cdf = build_cdf(LANGUAGE_WEIGHTS)
    # Release years skew recent.
    years = list(range(1985, 2026))
    year_cdf = build_cdf([1.03 ** (y - 1985) for y in years])

    w.begin_copy("film", [
        "film_id", "title", "description", "release_year", "language_id",
        "original_language_id", "rental_duration", "rental_rate", "length",
        "replacement_cost", "rating", "special_features", "last_update",
    ])

    used_titles: set = set()
    durations: dict[int, int] = {}

    for film_id in range(1, N_FILMS + 1):
        language_id = language_ids[sample_cdf(lang_cdf, rng)]

        original_language_id = None
        if rng.random() < 0.08:
            others = [lid for lid in language_ids if lid != language_id]
            original_language_id = rng.choice(others)

        rental_duration = rng.choice([3, 3, 3, 4, 4, 5, 5, 6, 7])
        durations[film_id] = rental_duration

        n_features = rng.choice([1, 1, 2, 2, 2, 3, 3, 4])
        features = ", ".join(sorted(rng.sample(SPECIAL_FEATURES, n_features)))

        w.raw(row(
            film_id,
            make_title(rng, used_titles),
            make_description(rng),
            years[sample_cdf(year_cdf, rng)],
            language_id,
            original_language_id,
            rental_duration,
            RENTAL_RATES[sample_cdf(_RATE_CDF, rng)],
            max(45, min(185, int(round(rng.gauss(112, 24))))),
            "{:.2f}".format(rng.randrange(999, 2999, 100) / 100.0),
            RATINGS[sample_cdf(_RATING_CDF, rng)],
            features,
            random_datetime(rng, *CATALOGUE_WINDOW),
        ))

    w.end_copy()
    w.note_sequence("film", "film_id", N_FILMS)
    return durations


def write_film_category(w: DumpWriter, rng: random.Random,
                        category_ids: list[int]) -> None:
    cat_cdf = build_cdf(CATEGORY_WEIGHTS)
    w.begin_copy("film_category", ["film_id", "category_id", "last_update"])
    for film_id in range(1, N_FILMS + 1):
        w.raw(row(
            film_id,
            category_ids[sample_cdf(cat_cdf, rng)],
            random_datetime(rng, *CATALOGUE_WINDOW),
        ))
    w.end_copy()


def write_film_actor(w: DumpWriter, rng: random.Random,
                     actor_popularity_order: list[int]) -> int:
    """2-5 actors per film, drawn Zipfian over the actor popularity ranking."""
    actor_cdf = zipf_cdf(len(actor_popularity_order), offset=ZIPF_OFFSET_ACTOR)
    cast_size_cdf = build_cdf([0.35, 0.35, 0.20, 0.10])  # -> 2, 3, 4, 5
    cast_sizes = [2, 3, 4, 5]

    w.begin_copy("film_actor", ["actor_id", "film_id", "last_update"])
    total = 0
    for film_id in range(1, N_FILMS + 1):
        wanted = cast_sizes[sample_cdf(cast_size_cdf, rng)]
        chosen: set = set()
        attempts = 0
        while len(chosen) < wanted and attempts < wanted * 20:
            chosen.add(actor_popularity_order[sample_cdf(actor_cdf, rng)])
            attempts += 1
        stamp = random_datetime(rng, *CATALOGUE_WINDOW)
        for actor_id in sorted(chosen):
            w.raw(row(actor_id, film_id, stamp))
            total += 1
    w.end_copy()
    return total


def write_customer(w: DumpWriter, rng: random.Random) -> dict[int, list[int]]:
    w.begin_copy("customer", [
        "customer_id", "store_id", "first_name", "last_name", "email",
        "active", "create_date", "last_update",
    ])
    by_store: dict[int, list[int]] = {1: [], 2: []}
    seen_emails: set = set()

    for customer_id in range(1, N_CUSTOMERS + 1):
        store_id = 1 if rng.random() < STORE_1_SHARE else 2
        by_store[store_id].append(customer_id)

        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)

        local = "{}.{}".format(
            "".join(ch for ch in first.lower() if ch.isalpha()),
            "".join(ch for ch in last.lower() if ch.isalpha()),
        )
        # VARCHAR(50): keep local part short enough for the id suffix + domain.
        max_local = 50 - len(EMAIL_DOMAIN) - 1 - len(str(customer_id)) - 1
        local = local[:max_local]
        email = "{}{}@{}".format(local, customer_id, EMAIL_DOMAIN)
        if email in seen_emails:      # cannot happen (id suffix), belt and braces
            email = None
        else:
            seen_emails.add(email)

        create_date = random_datetime(rng, *CUSTOMER_SIGNUP_WINDOW)
        w.raw(row(
            customer_id, store_id, first, last, email,
            rng.random() > 0.06,  # ~6% inactive
            create_date,
            create_date + timedelta(seconds=rng.randrange(86_400 * 400)),
        ))

    w.end_copy()
    w.note_sequence("customer", "customer_id", N_CUSTOMERS)
    return by_store


def write_inventory(w: DumpWriter, rng: random.Random,
                    film_popularity_order: list[int]) -> dict[int, list[int]]:
    """Every film gets at least one copy; the rest follow film popularity."""
    film_cdf = zipf_cdf(len(film_popularity_order), offset=ZIPF_OFFSET_FILM)

    films_for_copies = list(range(1, N_FILMS + 1))  # guaranteed first copy
    for _ in range(N_INVENTORY - N_FILMS):
        films_for_copies.append(film_popularity_order[sample_cdf(film_cdf, rng)])
    rng.shuffle(films_for_copies)

    store_1_rows = int(round(N_INVENTORY * STORE_1_SHARE))

    w.begin_copy("inventory", ["inventory_id", "film_id", "store_id", "last_update"])
    by_store: dict[int, list[tuple[int, int]]] = {1: [], 2: []}
    for idx, film_id in enumerate(films_for_copies):
        inventory_id = idx + 1
        store_id = 1 if idx < store_1_rows else 2
        by_store[store_id].append((inventory_id, film_id))
        w.raw(row(inventory_id, film_id, store_id,
                  random_datetime(rng, *CATALOGUE_WINDOW)))
    w.end_copy()
    w.note_sequence("inventory", "inventory_id", N_INVENTORY)
    return by_store


# ---------------------------------------------------------------------------
# Rentals
# ---------------------------------------------------------------------------


def build_month_buckets() -> tuple[list[tuple[int, int]], list[float]]:
    months, weights = [], []
    year = RENTAL_WINDOW_START.year
    while year <= RENTAL_WINDOW_END.year:
        for month in range(1, 13):
            months.append((year, month))
            weights.append(MONTH_WEIGHTS[month] * YEAR_WEIGHTS[year])
        year += 1
    return months, weights


def sample_rental_datetime(rng: random.Random, months, month_cdf, hour_cdf) -> datetime:
    year, month = months[sample_cdf(month_cdf, rng)]
    day = rng.randrange(1, calendar.monthrange(year, month)[1] + 1)
    hour = sample_cdf(hour_cdf, rng)
    return datetime(year, month, day, hour, rng.randrange(60), rng.randrange(60))


def generate_rentals(rng: random.Random,
                     inventory_by_store: dict[int, list[tuple[int, int]]],
                     customers_by_store: dict[int, list[int]],
                     film_rank: dict[int, int],
                     film_durations: dict[int, int]) -> list[tuple]:
    months, month_weights = build_month_buckets()
    month_cdf = build_cdf(month_weights)
    hour_cdf = build_cdf(HOUR_WEIGHTS)

    # Inventory copies ordered by the popularity of the film they hold, so a
    # Zipfian draw over position concentrates rentals on popular titles.
    inv_pools: dict[int, list[tuple[int, int]]] = {}
    inv_cdfs: dict[int, list[float]] = {}
    for store_id, rows in inventory_by_store.items():
        ordered = sorted(rows, key=lambda r: (film_rank[r[1]], r[0]))
        inv_pools[store_id] = ordered
        inv_cdfs[store_id] = zipf_cdf(len(ordered), offset=ZIPF_OFFSET_COPY)

    # Pareto-distributed customer propensities: a minority rent constantly.
    cust_pools: dict[int, list[int]] = {}
    cust_cdfs: dict[int, list[float]] = {}
    for store_id, ids in customers_by_store.items():
        cust_pools[store_id] = ids
        cust_cdfs[store_id] = build_cdf(pareto_weights(len(ids), rng))

    store_1_rentals = int(round(N_RENTALS * STORE_1_SHARE))
    plan = [(1, store_1_rentals), (2, N_RENTALS - store_1_rentals)]

    rentals: list[tuple] = []
    for store_id, count in plan:
        inv_pool = inv_pools[store_id]
        inv_cdf = inv_cdfs[store_id]
        home = cust_pools[store_id]
        home_cdf = cust_cdfs[store_id]
        other_id = 2 if store_id == 1 else 1
        away = cust_pools[other_id]
        away_cdf = cust_cdfs[other_id]

        for _ in range(count):
            inventory_id, film_id = inv_pool[sample_cdf(inv_cdf, rng)]
            if rng.random() < 0.90:                     # mostly the home store
                customer_id = home[sample_cdf(home_cdf, rng)]
            else:
                customer_id = away[sample_cdf(away_cdf, rng)]
            when = sample_rental_datetime(rng, months, month_cdf, hour_cdf)
            rentals.append((when, inventory_id, customer_id, film_durations[film_id]))

    # Sorting by timestamp makes rental_id monotonic in rental_date, as it would
    # be in a real system.  Python's sort is stable, so this stays deterministic.
    rentals.sort(key=lambda r: r[0])
    return rentals


def resolve_returns(rng: random.Random, rentals: list[tuple]) -> list:
    """Compute return_date, prevent overlapping loans of the same copy, and
    mark ~3% of rentals as still out (NULL) -- but only the most recent loan of
    any given inventory copy, so 'still out' is never contradicted later."""
    returns: list = [None] * len(rentals)
    last_rental_index: dict[int, int] = {}

    for idx, (when, inventory_id, _customer_id, duration) in enumerate(rentals):
        jitter_days = rng.choice([-2, -1, 0, 0, 0, 1, 1, 2, 3, 5])
        held = timedelta(days=duration + jitter_days,
                         hours=rng.randrange(-6, 19),
                         minutes=rng.randrange(60))
        if held < timedelta(hours=2):
            held = timedelta(hours=2, minutes=rng.randrange(60))
        returns[idx] = when + held

        previous = last_rental_index.get(inventory_id)
        if previous is not None and returns[previous] > when:
            # A copy must be back on the shelf before it can go out again.
            # Everything is resolved at whole-second granularity, because the
            # dump renders timestamps to the second -- sub-second arithmetic
            # here would round a "trimmed" return back onto the rental itself.
            previous_start = rentals[previous][0]
            gap = int((when - previous_start).total_seconds())
            if gap <= 1:
                shrink = 1
            else:
                shrink = min(gap, max(gap // 2, gap - 3600))
            returns[previous] = previous_start + timedelta(seconds=shrink)
        last_rental_index[inventory_id] = idx

    # Candidates for "still out": the final loan of each copy.
    candidates = sorted(last_rental_index.values())
    wanted = int(round(len(rentals) * UNRETURNED_FRACTION))
    wanted = min(wanted, len(candidates))
    for idx in rng.sample(candidates, wanted):
        returns[idx] = None

    return returns


def write_rentals(w: DumpWriter, rentals: list[tuple], returns: list) -> None:
    w.begin_copy("rental", [
        "rental_id", "rental_date", "inventory_id", "customer_id",
        "return_date", "last_update",
    ])
    chunk: list[str] = []
    append = chunk.append
    for idx, (when, inventory_id, customer_id, _duration) in enumerate(rentals):
        rental_id = idx + 1
        return_date = returns[idx]
        last_update = return_date if return_date is not None else when
        append(row(rental_id, when, inventory_id, customer_id,
                   return_date, last_update))
        if len(chunk) >= 20_000:
            w.raw("".join(chunk))
            chunk = []
            append = chunk.append
    if chunk:
        w.raw("".join(chunk))
    w.end_copy()
    w.note_sequence("rental", "rental_id", len(rentals))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_RATE_CDF = build_cdf(RENTAL_RATE_WEIGHTS)
_RATING_CDF = build_cdf(RATING_WEIGHTS)

HEADER = """\
-- Synthetic data for the Sakila-derived schema.
-- Generated by generate_dump.py (seed={seed}).  Deterministic: regenerating
-- with the same script and seed reproduces this file byte for byte.
--
-- Load with:  psql -d <database> -f dump.sql
-- Tables are emitted in foreign-key dependency order.

BEGIN;

""".format(seed=SEED)

FOOTER = """
COMMIT;
"""


def main(output_path: Path) -> None:
    random.seed(SEED)          # single seeding point -> byte-identical output
    rng = random                # every draw below comes from this one stream

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        w = DumpWriter(handle)
        w.raw(HEADER)

        language_ids = write_language(w)
        category_ids = write_category(w)
        write_store(w)
        actor_ids = write_actor(w, rng)

        # Popularity rankings: rank 0 is the biggest star / most-stocked title.
        actor_popularity_order = actor_ids[:]
        rng.shuffle(actor_popularity_order)

        film_durations = write_film(w, rng, language_ids)

        film_popularity_order = list(range(1, N_FILMS + 1))
        rng.shuffle(film_popularity_order)
        film_rank = {fid: i for i, fid in enumerate(film_popularity_order)}

        write_film_category(w, rng, category_ids)
        write_film_actor(w, rng, actor_popularity_order)

        customers_by_store = write_customer(w, rng)
        inventory_by_store = write_inventory(w, rng, film_popularity_order)

        rentals = generate_rentals(rng, inventory_by_store, customers_by_store,
                                   film_rank, film_durations)
        returns = resolve_returns(rng, rentals)
        write_rentals(w, rentals, returns)

        w.write_setvals()
        w.raw(FOOTER)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    main(target)