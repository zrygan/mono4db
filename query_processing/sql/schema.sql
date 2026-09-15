-- Schema for the Sakila database
-- Scoped down to only include the tables of our interest.
-- In this case we only have:
--  rental, 
--  inventory, 
--  film, 
--  film_actor, 
--  store, and 
--  film_category.
--
-- The documentation for the Sakila database is available here
-- https://dev.mysql.com/doc/sakila/en/.

DROP TABLE IF EXISTS rental CASCADE;
DROP TABLE IF EXISTS inventory CASCADE;
DROP TABLE IF EXISTS customer CASCADE;
DROP TABLE IF EXISTS store CASCADE;
DROP TABLE IF EXISTS film_category CASCADE;
DROP TABLE IF EXISTS film_actor CASCADE;
DROP TABLE IF EXISTS film CASCADE;
DROP TABLE IF EXISTS category CASCADE;
DROP TABLE IF EXISTS language CASCADE;
DROP TABLE IF EXISTS actor CASCADE;

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
