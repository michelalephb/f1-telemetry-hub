-- F1DB (https://github.com/f1db/f1db), CC BY 4.0: all time F1 results and statistics, our own copy.
-- Schema f1db is not exposed through the API; the loader writes through f1db_load (service role only).
create schema if not exists f1db;

CREATE TABLE IF NOT EXISTS f1db."chassis"
( "id" VARCHAR(100) NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "name" VARCHAR(100) NOT NULL
, "full_name" VARCHAR(100) NOT NULL
, CONSTRAINT "chss_pk" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS f1db."circuit"
( "id" VARCHAR(100) NOT NULL
, "name" VARCHAR(100) NOT NULL
, "full_name" VARCHAR(100) NOT NULL
, "previous_names" VARCHAR(255)
, "type" VARCHAR(6) NOT NULL
, "direction" VARCHAR(14) NOT NULL
, "place_name" VARCHAR(100) NOT NULL
, "country_id" VARCHAR(100) NOT NULL
, "latitude" DECIMAL(10,6) NOT NULL
, "longitude" DECIMAL(10,6) NOT NULL
, "length" DECIMAL(6,3) NOT NULL
, "turns" INTEGER NOT NULL
, "total_races_held" INTEGER NOT NULL
, CONSTRAINT "crct_pk" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS f1db."circuit_layout"
( "id" VARCHAR(100) NOT NULL
, "circuit_id" VARCHAR(100) NOT NULL
, "effective" BOOLEAN NOT NULL
, "length" DECIMAL(6,3) NOT NULL
, "turns" INTEGER NOT NULL
, CONSTRAINT "ctlt" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS f1db."constructor"
( "id" VARCHAR(100) NOT NULL
, "name" VARCHAR(100) NOT NULL
, "full_name" VARCHAR(100) NOT NULL
, "country_id" VARCHAR(100) NOT NULL
, "best_championship_position" INTEGER
, "best_starting_grid_position" INTEGER
, "best_race_result" INTEGER
, "best_sprint_race_result" INTEGER
, "total_championship_wins" INTEGER NOT NULL
, "total_race_entries" INTEGER NOT NULL
, "total_race_starts" INTEGER NOT NULL
, "total_race_wins" INTEGER NOT NULL
, "total_1_and_2_finishes" INTEGER NOT NULL
, "total_race_laps" INTEGER NOT NULL
, "total_podiums" INTEGER NOT NULL
, "total_podium_races" INTEGER NOT NULL
, "total_points" DECIMAL(8,2) NOT NULL
, "total_championship_points" DECIMAL(8,2) NOT NULL
, "total_pole_positions" INTEGER NOT NULL
, "total_fastest_laps" INTEGER NOT NULL
, "total_sprint_race_starts" INTEGER NOT NULL
, "total_sprint_race_wins" INTEGER NOT NULL
, CONSTRAINT "cnst_pk" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS f1db."constructor_chronology"
( "constructor_id" VARCHAR(100) NOT NULL
, "position_display_order" INTEGER NOT NULL
, "other_constructor_id" VARCHAR(100) NOT NULL
, "year_from" INTEGER NOT NULL
, "year_to" INTEGER
, CONSTRAINT "cnch_pk" PRIMARY KEY ("constructor_id", "position_display_order")
, CONSTRAINT "cnch_constructor_id_other_constructor_id_year_from_year_to_uk" UNIQUE ("constructor_id", "other_constructor_id", "year_from", "year_to")
);

CREATE TABLE IF NOT EXISTS f1db."continent"
( "id" VARCHAR(100) NOT NULL
, "code" VARCHAR(2) NOT NULL
, "name" VARCHAR(100) NOT NULL
, "demonym" VARCHAR(100) NOT NULL
, CONSTRAINT "cntn_pk" PRIMARY KEY ("id")
, CONSTRAINT "cntn_code_uk" UNIQUE ("code")
, CONSTRAINT "cntn_name_uk" UNIQUE ("name")
);

CREATE TABLE IF NOT EXISTS f1db."country"
( "id" VARCHAR(100) NOT NULL
, "alpha2_code" VARCHAR(2) NOT NULL
, "alpha3_code" VARCHAR(3) NOT NULL
, "ioc_code" VARCHAR(3)
, "name" VARCHAR(100) NOT NULL
, "demonym" VARCHAR(100)
, "continent_id" VARCHAR(100) NOT NULL
, CONSTRAINT "cntr_pk" PRIMARY KEY ("id")
, CONSTRAINT "cntr_alpha2_code_uk" UNIQUE ("alpha2_code")
, CONSTRAINT "cntr_alpha3_code_uk" UNIQUE ("alpha3_code")
, CONSTRAINT "cntr_name_uk" UNIQUE ("name")
);

CREATE TABLE IF NOT EXISTS f1db."driver"
( "id" VARCHAR(100) NOT NULL
, "name" VARCHAR(100) NOT NULL
, "first_name" VARCHAR(100) NOT NULL
, "last_name" VARCHAR(100) NOT NULL
, "full_name" VARCHAR(100) NOT NULL
, "abbreviation" VARCHAR(3) NOT NULL
, "permanent_number" VARCHAR(2)
, "gender" VARCHAR(6) NOT NULL
, "date_of_birth" DATE NOT NULL
, "date_of_death" DATE
, "place_of_birth" VARCHAR(100) NOT NULL
, "country_of_birth_country_id" VARCHAR(100) NOT NULL
, "nationality_country_id" VARCHAR(100) NOT NULL
, "second_nationality_country_id" VARCHAR(100)
, "best_championship_position" INTEGER
, "best_starting_grid_position" INTEGER
, "best_race_result" INTEGER
, "best_sprint_race_result" INTEGER
, "total_championship_wins" INTEGER NOT NULL
, "total_race_entries" INTEGER NOT NULL
, "total_race_starts" INTEGER NOT NULL
, "total_race_wins" INTEGER NOT NULL
, "total_race_laps" INTEGER NOT NULL
, "total_podiums" INTEGER NOT NULL
, "total_points" DECIMAL(8,2) NOT NULL
, "total_championship_points" DECIMAL(8,2) NOT NULL
, "total_pole_positions" INTEGER NOT NULL
, "total_fastest_laps" INTEGER NOT NULL
, "total_sprint_race_starts" INTEGER NOT NULL
, "total_sprint_race_wins" INTEGER NOT NULL
, "total_driver_of_the_day" INTEGER NOT NULL
, "total_grand_slams" INTEGER NOT NULL
, CONSTRAINT "drvr_pk" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS f1db."driver_family_relationship"
( "driver_id" VARCHAR(100) NOT NULL
, "position_display_order" INTEGER NOT NULL
, "other_driver_id" VARCHAR(100) NOT NULL
, "type" VARCHAR(50) NOT NULL
, CONSTRAINT "dfrl_pk" PRIMARY KEY ("driver_id", "position_display_order")
, CONSTRAINT "dfrl_driver_id_other_driver_id_type_uk" UNIQUE ("driver_id", "other_driver_id", "type")
);

CREATE TABLE IF NOT EXISTS f1db."engine"
( "id" VARCHAR(100) NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, "name" VARCHAR(100) NOT NULL
, "full_name" VARCHAR(100) NOT NULL
, "capacity" DECIMAL(2,1)
, "configuration" VARCHAR(100)
, "aspiration" VARCHAR(100)
, CONSTRAINT "engn_pk" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS f1db."engine_manufacturer"
( "id" VARCHAR(100) NOT NULL
, "name" VARCHAR(100) NOT NULL
, "country_id" VARCHAR(100) NOT NULL
, "best_championship_position" INTEGER
, "best_starting_grid_position" INTEGER
, "best_race_result" INTEGER
, "best_sprint_race_result" INTEGER
, "total_championship_wins" INTEGER NOT NULL
, "total_race_entries" INTEGER NOT NULL
, "total_race_starts" INTEGER NOT NULL
, "total_race_wins" INTEGER NOT NULL
, "total_race_laps" INTEGER NOT NULL
, "total_podiums" INTEGER NOT NULL
, "total_podium_races" INTEGER NOT NULL
, "total_points" DECIMAL(8,2) NOT NULL
, "total_championship_points" DECIMAL(8,2) NOT NULL
, "total_pole_positions" INTEGER NOT NULL
, "total_fastest_laps" INTEGER NOT NULL
, "total_sprint_race_starts" INTEGER NOT NULL
, "total_sprint_race_wins" INTEGER NOT NULL
, CONSTRAINT "enmf_pk" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS f1db."entrant"
( "id" VARCHAR(100) NOT NULL
, "name" VARCHAR(100) NOT NULL
, CONSTRAINT "entr_pk" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS f1db."grand_prix"
( "id" VARCHAR(100) NOT NULL
, "name" VARCHAR(100) NOT NULL
, "full_name" VARCHAR(100) NOT NULL
, "short_name" VARCHAR(100) NOT NULL
, "abbreviation" VARCHAR(3) NOT NULL
, "country_id" VARCHAR(100)
, "total_races_held" INTEGER NOT NULL
, CONSTRAINT "grpx_pk" PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS f1db."race"
( "id" INTEGER NOT NULL
, "year" INTEGER NOT NULL
, "round" INTEGER NOT NULL
, "date" DATE NOT NULL
, "time" VARCHAR(5)
, "grand_prix_id" VARCHAR(100) NOT NULL
, "official_name" VARCHAR(100) NOT NULL
, "qualifying_format" VARCHAR(20) NOT NULL
, "sprint_qualifying_format" VARCHAR(20)
, "circuit_id" VARCHAR(100) NOT NULL
, "circuit_layout_id" VARCHAR(100) NOT NULL
, "circuit_type" VARCHAR(6) NOT NULL
, "direction" VARCHAR(14) NOT NULL
, "course_length" DECIMAL(6,3) NOT NULL
, "turns" INTEGER NOT NULL
, "laps" INTEGER NOT NULL
, "distance" DECIMAL(6,3) NOT NULL
, "scheduled_laps" INTEGER
, "scheduled_distance" DECIMAL(6,3)
, "drivers_championship_decider" BOOLEAN NOT NULL
, "constructors_championship_decider" BOOLEAN NOT NULL
, "pre_qualifying_date" DATE
, "pre_qualifying_time" VARCHAR(5)
, "free_practice_1_date" DATE
, "free_practice_1_time" VARCHAR(5)
, "free_practice_2_date" DATE
, "free_practice_2_time" VARCHAR(5)
, "free_practice_3_date" DATE
, "free_practice_3_time" VARCHAR(5)
, "free_practice_4_date" DATE
, "free_practice_4_time" VARCHAR(5)
, "qualifying_1_date" DATE
, "qualifying_1_time" VARCHAR(5)
, "qualifying_2_date" DATE
, "qualifying_2_time" VARCHAR(5)
, "qualifying_date" DATE
, "qualifying_time" VARCHAR(5)
, "sprint_qualifying_date" DATE
, "sprint_qualifying_time" VARCHAR(5)
, "sprint_race_date" DATE
, "sprint_race_time" VARCHAR(5)
, "sprint_race_laps" INTEGER
, "sprint_race_distance" DECIMAL(6,3)
, "sprint_race_scheduled_laps" INTEGER
, "sprint_race_scheduled_distance" DECIMAL(6,3)
, "warming_up_date" DATE
, "warming_up_time" VARCHAR(5)
, CONSTRAINT "race_pk" PRIMARY KEY ("id")
, CONSTRAINT "race_year_round_uk" UNIQUE ("year", "round")
);

CREATE TABLE IF NOT EXISTS f1db."race_constructor_standing"
( "race_id" INTEGER NOT NULL
, "position_display_order" INTEGER NOT NULL
, "position_number" INTEGER
, "position_text" VARCHAR(4) NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, "points" DECIMAL(8,2) NOT NULL
, "positions_gained" INTEGER
, "championship_won" BOOLEAN NOT NULL
, CONSTRAINT "rccs_pk" PRIMARY KEY ("race_id", "position_display_order")
);

CREATE TABLE IF NOT EXISTS f1db."race_data"
( "race_id" INTEGER NOT NULL
, "type" VARCHAR(50) NOT NULL
, "position_display_order" INTEGER NOT NULL
, "position_number" INTEGER
, "position_text" VARCHAR(4) NOT NULL
, "driver_number" VARCHAR(3) NOT NULL
, "driver_id" VARCHAR(100) NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, "tyre_manufacturer_id" VARCHAR(100) NOT NULL
, "practice_time" VARCHAR(20)
, "practice_time_millis" INTEGER
, "practice_gap" VARCHAR(20)
, "practice_gap_millis" INTEGER
, "practice_interval" VARCHAR(20)
, "practice_interval_millis" INTEGER
, "practice_laps" INTEGER
, "qualifying_time" VARCHAR(20)
, "qualifying_time_millis" INTEGER
, "qualifying_q1" VARCHAR(20)
, "qualifying_q1_millis" INTEGER
, "qualifying_q2" VARCHAR(20)
, "qualifying_q2_millis" INTEGER
, "qualifying_q3" VARCHAR(20)
, "qualifying_q3_millis" INTEGER
, "qualifying_gap" VARCHAR(20)
, "qualifying_gap_millis" INTEGER
, "qualifying_interval" VARCHAR(20)
, "qualifying_interval_millis" INTEGER
, "qualifying_laps" INTEGER
, "starting_grid_position_qualification_position_number" INTEGER
, "starting_grid_position_qualification_position_text" VARCHAR(4)
, "starting_grid_position_grid_penalty" VARCHAR(20)
, "starting_grid_position_grid_penalty_positions" INTEGER
, "starting_grid_position_time" VARCHAR(20)
, "starting_grid_position_time_millis" INTEGER
, "race_shared_car" BOOLEAN
, "race_laps" INTEGER
, "race_time" VARCHAR(20)
, "race_time_millis" INTEGER
, "race_time_penalty" VARCHAR(20)
, "race_time_penalty_millis" INTEGER
, "race_gap" VARCHAR(20)
, "race_gap_millis" INTEGER
, "race_gap_laps" INTEGER
, "race_interval" VARCHAR(20)
, "race_interval_millis" INTEGER
, "race_reason_retired" VARCHAR(100)
, "race_points" DECIMAL(8,2)
, "race_pole_position" BOOLEAN
, "race_qualification_position_number" INTEGER
, "race_qualification_position_text" VARCHAR(4)
, "race_grid_position_number" INTEGER
, "race_grid_position_text" VARCHAR(2)
, "race_positions_gained" INTEGER
, "race_pit_stops" INTEGER
, "race_fastest_lap" BOOLEAN
, "race_driver_of_the_day" BOOLEAN
, "race_grand_slam" BOOLEAN
, "fastest_lap_lap" INTEGER
, "fastest_lap_time" VARCHAR(20)
, "fastest_lap_time_millis" INTEGER
, "fastest_lap_gap" VARCHAR(20)
, "fastest_lap_gap_millis" INTEGER
, "fastest_lap_interval" VARCHAR(20)
, "fastest_lap_interval_millis" INTEGER
, "pit_stop_stop" INTEGER
, "pit_stop_lap" INTEGER
, "pit_stop_time" VARCHAR(20)
, "pit_stop_time_millis" INTEGER
, "driver_of_the_day_percentage" DECIMAL(5,2)
, CONSTRAINT "rcda_pk" PRIMARY KEY ("race_id", "type", "position_display_order")
);

CREATE TABLE IF NOT EXISTS f1db."race_driver_standing"
( "race_id" INTEGER NOT NULL
, "position_display_order" INTEGER NOT NULL
, "position_number" INTEGER
, "position_text" VARCHAR(4) NOT NULL
, "driver_id" VARCHAR(100) NOT NULL
, "points" DECIMAL(8,2) NOT NULL
, "positions_gained" INTEGER
, "championship_won" BOOLEAN NOT NULL
, CONSTRAINT "rcds_pk" PRIMARY KEY ("race_id", "position_display_order")
);

CREATE TABLE IF NOT EXISTS f1db."season"
( "year" INTEGER NOT NULL
, CONSTRAINT "sson_pk" PRIMARY KEY ("year")
);

CREATE TABLE IF NOT EXISTS f1db."season_constructor"
( "year" INTEGER NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "position_number" INTEGER
, "position_text" VARCHAR(4)
, "best_starting_grid_position" INTEGER
, "best_race_result" INTEGER
, "best_sprint_race_result" INTEGER
, "total_race_entries" INTEGER NOT NULL
, "total_race_starts" INTEGER NOT NULL
, "total_race_wins" INTEGER NOT NULL
, "total_1_and_2_finishes" INTEGER NOT NULL
, "total_race_laps" INTEGER NOT NULL
, "total_podiums" INTEGER NOT NULL
, "total_podium_races" INTEGER NOT NULL
, "total_points" DECIMAL(8,2) NOT NULL
, "total_pole_positions" INTEGER NOT NULL
, "total_fastest_laps" INTEGER NOT NULL
, "total_sprint_race_starts" INTEGER NOT NULL
, "total_sprint_race_wins" INTEGER NOT NULL
, CONSTRAINT "sscn_pk" PRIMARY KEY ("year", "constructor_id")
);

CREATE TABLE IF NOT EXISTS f1db."season_constructor_standing"
( "year" INTEGER NOT NULL
, "position_display_order" INTEGER NOT NULL
, "position_number" INTEGER
, "position_text" VARCHAR(4) NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, "points" DECIMAL(8,2) NOT NULL
, "championship_won" BOOLEAN NOT NULL
, CONSTRAINT "sscs_pk" PRIMARY KEY ("year", "position_display_order")
);

CREATE TABLE IF NOT EXISTS f1db."season_driver"
( "year" INTEGER NOT NULL
, "driver_id" VARCHAR(100) NOT NULL
, "position_number" INTEGER
, "position_text" VARCHAR(4)
, "best_starting_grid_position" INTEGER
, "best_race_result" INTEGER
, "best_sprint_race_result" INTEGER
, "total_race_entries" INTEGER NOT NULL
, "total_race_starts" INTEGER NOT NULL
, "total_race_wins" INTEGER NOT NULL
, "total_race_laps" INTEGER NOT NULL
, "total_podiums" INTEGER NOT NULL
, "total_points" DECIMAL(8,2) NOT NULL
, "total_pole_positions" INTEGER NOT NULL
, "total_fastest_laps" INTEGER NOT NULL
, "total_sprint_race_starts" INTEGER NOT NULL
, "total_sprint_race_wins" INTEGER NOT NULL
, "total_driver_of_the_day" INTEGER NOT NULL
, "total_grand_slams" INTEGER NOT NULL
, CONSTRAINT "ssdr_pk" PRIMARY KEY ("year", "driver_id")
);

CREATE TABLE IF NOT EXISTS f1db."season_driver_standing"
( "year" INTEGER NOT NULL
, "position_display_order" INTEGER NOT NULL
, "position_number" INTEGER
, "position_text" VARCHAR(4) NOT NULL
, "driver_id" VARCHAR(100) NOT NULL
, "points" DECIMAL(8,2) NOT NULL
, "championship_won" BOOLEAN NOT NULL
, CONSTRAINT "ssds_pk" PRIMARY KEY ("year", "position_display_order")
);

CREATE TABLE IF NOT EXISTS f1db."season_engine_manufacturer"
( "year" INTEGER NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, "position_number" INTEGER
, "position_text" VARCHAR(4)
, "best_starting_grid_position" INTEGER
, "best_race_result" INTEGER
, "best_sprint_race_result" INTEGER
, "total_race_entries" INTEGER NOT NULL
, "total_race_starts" INTEGER NOT NULL
, "total_race_wins" INTEGER NOT NULL
, "total_race_laps" INTEGER NOT NULL
, "total_podiums" INTEGER NOT NULL
, "total_podium_races" INTEGER NOT NULL
, "total_points" DECIMAL(8,2) NOT NULL
, "total_pole_positions" INTEGER NOT NULL
, "total_fastest_laps" INTEGER NOT NULL
, "total_sprint_race_starts" INTEGER NOT NULL
, "total_sprint_race_wins" INTEGER NOT NULL
, CONSTRAINT "ssem_pk" PRIMARY KEY ("year", "engine_manufacturer_id")
);

CREATE TABLE IF NOT EXISTS f1db."season_entrant"
( "year" INTEGER NOT NULL
, "entrant_id" VARCHAR(100) NOT NULL
, "country_id" VARCHAR(100) NOT NULL
, CONSTRAINT "sent_pk" PRIMARY KEY ("year", "entrant_id")
);

CREATE TABLE IF NOT EXISTS f1db."season_entrant_chassis"
( "year" INTEGER NOT NULL
, "entrant_id" VARCHAR(100) NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, "chassis_id" VARCHAR(100) NOT NULL
, CONSTRAINT "sech_pk" PRIMARY KEY ("year", "entrant_id", "constructor_id", "engine_manufacturer_id", "chassis_id")
);

CREATE TABLE IF NOT EXISTS f1db."season_entrant_constructor"
( "year" INTEGER NOT NULL
, "entrant_id" VARCHAR(100) NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, CONSTRAINT "secn_pk" PRIMARY KEY ("year", "entrant_id", "constructor_id", "engine_manufacturer_id")
);

CREATE TABLE IF NOT EXISTS f1db."season_entrant_driver"
( "year" INTEGER NOT NULL
, "entrant_id" VARCHAR(100) NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, "driver_id" VARCHAR(100) NOT NULL
, "rounds" VARCHAR(100)
, "rounds_text" VARCHAR(100)
, "test_driver" BOOLEAN NOT NULL
, CONSTRAINT "sedr_pk" PRIMARY KEY ("year", "entrant_id", "constructor_id", "engine_manufacturer_id", "driver_id")
);

CREATE TABLE IF NOT EXISTS f1db."season_entrant_engine"
( "year" INTEGER NOT NULL
, "entrant_id" VARCHAR(100) NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, "engine_id" VARCHAR(100) NOT NULL
, CONSTRAINT "seen_pk" PRIMARY KEY ("year", "entrant_id", "constructor_id", "engine_manufacturer_id", "engine_id")
);

CREATE TABLE IF NOT EXISTS f1db."season_entrant_tyre_manufacturer"
( "year" INTEGER NOT NULL
, "entrant_id" VARCHAR(100) NOT NULL
, "constructor_id" VARCHAR(100) NOT NULL
, "engine_manufacturer_id" VARCHAR(100) NOT NULL
, "tyre_manufacturer_id" VARCHAR(100) NOT NULL
, CONSTRAINT "setm_pk" PRIMARY KEY ("year", "entrant_id", "constructor_id", "engine_manufacturer_id", "tyre_manufacturer_id")
);

CREATE TABLE IF NOT EXISTS f1db."season_tyre_manufacturer"
( "year" INTEGER NOT NULL
, "tyre_manufacturer_id" VARCHAR(100) NOT NULL
, "best_starting_grid_position" INTEGER
, "best_race_result" INTEGER
, "best_sprint_race_result" INTEGER
, "total_race_entries" INTEGER NOT NULL
, "total_race_starts" INTEGER NOT NULL
, "total_race_wins" INTEGER NOT NULL
, "total_race_laps" INTEGER NOT NULL
, "total_podiums" INTEGER NOT NULL
, "total_podium_races" INTEGER NOT NULL
, "total_pole_positions" INTEGER NOT NULL
, "total_fastest_laps" INTEGER NOT NULL
, "total_sprint_race_starts" INTEGER NOT NULL
, "total_sprint_race_wins" INTEGER NOT NULL
, CONSTRAINT "sstm_pk" PRIMARY KEY ("year", "tyre_manufacturer_id")
);

CREATE TABLE IF NOT EXISTS f1db."tyre_manufacturer"
( "id" VARCHAR(100) NOT NULL
, "name" VARCHAR(100) NOT NULL
, "country_id" VARCHAR(100) NOT NULL
, "best_starting_grid_position" INTEGER
, "best_race_result" INTEGER
, "best_sprint_race_result" INTEGER
, "total_race_entries" INTEGER NOT NULL
, "total_race_starts" INTEGER NOT NULL
, "total_race_wins" INTEGER NOT NULL
, "total_race_laps" INTEGER NOT NULL
, "total_podiums" INTEGER NOT NULL
, "total_podium_races" INTEGER NOT NULL
, "total_pole_positions" INTEGER NOT NULL
, "total_fastest_laps" INTEGER NOT NULL
, "total_sprint_race_starts" INTEGER NOT NULL
, "total_sprint_race_wins" INTEGER NOT NULL
, CONSTRAINT "tymf_pk" PRIMARY KEY ("id")
);

CREATE OR REPLACE VIEW f1db."driver_of_the_day_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."driver_of_the_day_percentage" AS "percentage"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'DRIVER_OF_THE_DAY_RESULT';

CREATE OR REPLACE VIEW f1db."fastest_lap" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."fastest_lap_lap" AS "lap"
,        "race_data"."fastest_lap_time" AS "time"
,        "race_data"."fastest_lap_time_millis" AS "time_millis"
,        "race_data"."fastest_lap_gap" AS "gap"
,        "race_data"."fastest_lap_gap_millis" AS "gap_millis"
,        "race_data"."fastest_lap_interval" AS "interval"
,        "race_data"."fastest_lap_interval_millis" AS "interval_millis"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'FASTEST_LAP';

CREATE OR REPLACE VIEW f1db."free_practice_1_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."practice_time" AS "time"
,        "race_data"."practice_time_millis" AS "time_millis"
,        "race_data"."practice_gap" AS "gap"
,        "race_data"."practice_gap_millis" AS "gap_millis"
,        "race_data"."practice_interval" AS "interval"
,        "race_data"."practice_interval_millis" AS "interval_millis"
,        "race_data"."practice_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'FREE_PRACTICE_1_RESULT';

CREATE OR REPLACE VIEW f1db."free_practice_2_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."practice_time" AS "time"
,        "race_data"."practice_time_millis" AS "time_millis"
,        "race_data"."practice_gap" AS "gap"
,        "race_data"."practice_gap_millis" AS "gap_millis"
,        "race_data"."practice_interval" AS "interval"
,        "race_data"."practice_interval_millis" AS "interval_millis"
,        "race_data"."practice_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'FREE_PRACTICE_2_RESULT';

CREATE OR REPLACE VIEW f1db."free_practice_3_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."practice_time" AS "time"
,        "race_data"."practice_time_millis" AS "time_millis"
,        "race_data"."practice_gap" AS "gap"
,        "race_data"."practice_gap_millis" AS "gap_millis"
,        "race_data"."practice_interval" AS "interval"
,        "race_data"."practice_interval_millis" AS "interval_millis"
,        "race_data"."practice_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'FREE_PRACTICE_3_RESULT';

CREATE OR REPLACE VIEW f1db."free_practice_4_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."practice_time" AS "time"
,        "race_data"."practice_time_millis" AS "time_millis"
,        "race_data"."practice_gap" AS "gap"
,        "race_data"."practice_gap_millis" AS "gap_millis"
,        "race_data"."practice_interval" AS "interval"
,        "race_data"."practice_interval_millis" AS "interval_millis"
,        "race_data"."practice_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'FREE_PRACTICE_4_RESULT';

CREATE OR REPLACE VIEW f1db."pit_stop" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."pit_stop_stop" AS "stop"
,        "race_data"."pit_stop_lap" AS "lap"
,        "race_data"."pit_stop_time" AS "time"
,        "race_data"."pit_stop_time_millis" AS "time_millis"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'PIT_STOP';

CREATE OR REPLACE VIEW f1db."pre_qualifying_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."qualifying_time" AS "time"
,        "race_data"."qualifying_time_millis" AS "time_millis"
,        "race_data"."qualifying_gap" AS "gap"
,        "race_data"."qualifying_gap_millis" AS "gap_millis"
,        "race_data"."qualifying_interval" AS "interval"
,        "race_data"."qualifying_interval_millis" AS "interval_millis"
,        "race_data"."qualifying_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'PRE_QUALIFYING_RESULT';

CREATE OR REPLACE VIEW f1db."qualifying_1_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."qualifying_time" AS "time"
,        "race_data"."qualifying_time_millis" AS "time_millis"
,        "race_data"."qualifying_gap" AS "gap"
,        "race_data"."qualifying_gap_millis" AS "gap_millis"
,        "race_data"."qualifying_interval" AS "interval"
,        "race_data"."qualifying_interval_millis" AS "interval_millis"
,        "race_data"."qualifying_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'QUALIFYING_1_RESULT';

CREATE OR REPLACE VIEW f1db."qualifying_2_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."qualifying_time" AS "time"
,        "race_data"."qualifying_time_millis" AS "time_millis"
,        "race_data"."qualifying_gap" AS "gap"
,        "race_data"."qualifying_gap_millis" AS "gap_millis"
,        "race_data"."qualifying_interval" AS "interval"
,        "race_data"."qualifying_interval_millis" AS "interval_millis"
,        "race_data"."qualifying_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'QUALIFYING_2_RESULT';

CREATE OR REPLACE VIEW f1db."qualifying_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."qualifying_time" AS "time"
,        "race_data"."qualifying_time_millis" AS "time_millis"
,        "race_data"."qualifying_q1" AS "q1"
,        "race_data"."qualifying_q1_millis" AS "q1_millis"
,        "race_data"."qualifying_q2" AS "q2"
,        "race_data"."qualifying_q2_millis" AS "q2_millis"
,        "race_data"."qualifying_q3" AS "q3"
,        "race_data"."qualifying_q3_millis" AS "q3_millis"
,        "race_data"."qualifying_gap" AS "gap"
,        "race_data"."qualifying_gap_millis" AS "gap_millis"
,        "race_data"."qualifying_interval" AS "interval"
,        "race_data"."qualifying_interval_millis" AS "interval_millis"
,        "race_data"."qualifying_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'QUALIFYING_RESULT';

CREATE OR REPLACE VIEW f1db."race_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."race_shared_car" AS "shared_car"
,        "race_data"."race_laps" AS "laps"
,        "race_data"."race_time" AS "time"
,        "race_data"."race_time_millis" AS "time_millis"
,        "race_data"."race_time_penalty" AS "time_penalty"
,        "race_data"."race_time_penalty_millis" AS "time_penalty_millis"
,        "race_data"."race_gap" AS "gap"
,        "race_data"."race_gap_millis" AS "gap_millis"
,        "race_data"."race_gap_laps" AS "gap_laps"
,        "race_data"."race_interval" AS "interval"
,        "race_data"."race_interval_millis" AS "interval_millis"
,        "race_data"."race_reason_retired" AS "reason_retired"
,        "race_data"."race_points" AS "points"
,        "race_data"."race_pole_position" AS "pole_position"
,        "race_data"."race_qualification_position_number" AS "qualification_position_number"
,        "race_data"."race_qualification_position_text" AS "qualification_position_text"
,        "race_data"."race_grid_position_number" AS "grid_position_number"
,        "race_data"."race_grid_position_text" AS "grid_position_text"
,        "race_data"."race_positions_gained" AS "positions_gained"
,        "race_data"."race_pit_stops" AS "pit_stops"
,        "race_data"."race_fastest_lap" AS "fastest_lap"
,        "race_data"."race_driver_of_the_day" AS "driver_of_the_day"
,        "race_data"."race_grand_slam" AS "grand_slam"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'RACE_RESULT';

CREATE OR REPLACE VIEW f1db."sprint_qualifying_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."qualifying_time" AS "time"
,        "race_data"."qualifying_time_millis" AS "time_millis"
,        "race_data"."qualifying_q1" AS "q1"
,        "race_data"."qualifying_q1_millis" AS "q1_millis"
,        "race_data"."qualifying_q2" AS "q2"
,        "race_data"."qualifying_q2_millis" AS "q2_millis"
,        "race_data"."qualifying_q3" AS "q3"
,        "race_data"."qualifying_q3_millis" AS "q3_millis"
,        "race_data"."qualifying_gap" AS "gap"
,        "race_data"."qualifying_gap_millis" AS "gap_millis"
,        "race_data"."qualifying_interval" AS "interval"
,        "race_data"."qualifying_interval_millis" AS "interval_millis"
,        "race_data"."qualifying_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'SPRINT_QUALIFYING_RESULT';

CREATE OR REPLACE VIEW f1db."sprint_race_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."race_laps" AS "laps"
,        "race_data"."race_time" AS "time"
,        "race_data"."race_time_millis" AS "time_millis"
,        "race_data"."race_time_penalty" AS "time_penalty"
,        "race_data"."race_time_penalty_millis" AS "time_penalty_millis"
,        "race_data"."race_gap" AS "gap"
,        "race_data"."race_gap_millis" AS "gap_millis"
,        "race_data"."race_gap_laps" AS "gap_laps"
,        "race_data"."race_interval" AS "interval"
,        "race_data"."race_interval_millis" AS "interval_millis"
,        "race_data"."race_reason_retired" AS "reason_retired"
,        "race_data"."race_points" AS "points"
,        "race_data"."race_qualification_position_number" AS "qualification_position_number"
,        "race_data"."race_qualification_position_text" AS "qualification_position_text"
,        "race_data"."race_grid_position_number" AS "grid_position_number"
,        "race_data"."race_grid_position_text" AS "grid_position_text"
,        "race_data"."race_positions_gained" AS "positions_gained"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'SPRINT_RACE_RESULT';

CREATE OR REPLACE VIEW f1db."sprint_starting_grid_position" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."starting_grid_position_qualification_position_number" AS "qualification_position_number"
,        "race_data"."starting_grid_position_qualification_position_text" AS "qualification_position_text"
,        "race_data"."starting_grid_position_grid_penalty" AS "grid_penalty"
,        "race_data"."starting_grid_position_grid_penalty_positions" AS "grid_penalty_positions"
,        "race_data"."starting_grid_position_time" AS "time"
,        "race_data"."starting_grid_position_time_millis" AS "time_millis"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'SPRINT_STARTING_GRID_POSITION';

CREATE OR REPLACE VIEW f1db."starting_grid_position" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."starting_grid_position_qualification_position_number" AS "qualification_position_number"
,        "race_data"."starting_grid_position_qualification_position_text" AS "qualification_position_text"
,        "race_data"."starting_grid_position_grid_penalty" AS "grid_penalty"
,        "race_data"."starting_grid_position_grid_penalty_positions" AS "grid_penalty_positions"
,        "race_data"."starting_grid_position_time" AS "time"
,        "race_data"."starting_grid_position_time_millis" AS "time_millis"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'STARTING_GRID_POSITION';

CREATE OR REPLACE VIEW f1db."warming_up_result" AS
SELECT   "race_data"."race_id"
,        "race_data"."position_display_order"
,        "race_data"."position_number"
,        "race_data"."position_text"
,        "race_data"."driver_number"
,        "race_data"."driver_id"
,        "race_data"."constructor_id"
,        "race_data"."engine_manufacturer_id"
,        "race_data"."tyre_manufacturer_id"
,        "race_data"."practice_time" AS "time"
,        "race_data"."practice_time_millis" AS "time_millis"
,        "race_data"."practice_gap" AS "gap"
,        "race_data"."practice_gap_millis" AS "gap_millis"
,        "race_data"."practice_interval" AS "interval"
,        "race_data"."practice_interval_millis" AS "interval_millis"
,        "race_data"."practice_laps" AS "laps"
FROM f1db."race_data"
WHERE    "race_data"."type" = 'WARMING_UP_RESULT';

create table if not exists f1db._meta (
  id int primary key default 1 check (id = 1),
  version text, released_at timestamptz, loaded_at timestamptz, row_count int,
  source text default 'https://github.com/f1db/f1db', license text default 'CC BY 4.0'
);

-- Bulk loader for GitHub Actions (service role): replace the rows of one F1DB table.
create or replace function public.f1db_load(tab text, rows jsonb, wipe boolean default false)
returns int language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  if not exists (select 1 from information_schema.tables where table_schema = 'f1db' and table_name = tab and table_type = 'BASE TABLE') then
    raise exception 'unknown f1db table %', tab;
  end if;
  if wipe then execute format('truncate table f1db.%I', tab); end if;
  execute format('insert into f1db.%I select * from jsonb_populate_recordset(null::f1db.%I, $1)', tab, tab) using rows;
  get diagnostics n = row_count;
  return n;
end $$;
revoke all on function public.f1db_load(text, jsonb, boolean) from public, anon, authenticated;
grant execute on function public.f1db_load(text, jsonb, boolean) to service_role;

create or replace function public.f1db_stamp(ver text, released timestamptz, total int)
returns void language sql security definer set search_path = '' as $$
  insert into f1db._meta (id, version, released_at, loaded_at, row_count) values (1, ver, released, now(), total)
  on conflict (id) do update set version = excluded.version, released_at = excluded.released_at, loaded_at = excluded.loaded_at, row_count = excluded.row_count;
$$;
revoke all on function public.f1db_stamp(text, timestamptz, int) from public, anon, authenticated;
grant execute on function public.f1db_stamp(text, timestamptz, int) to service_role;
