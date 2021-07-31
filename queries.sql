--name: get_random_question
SELECT q.id,
       c.title as category,
       c.comment as comment,
       c.show_year as year,
       q.value as value,
       q.question,
       q.answer
FROM   question q
       LEFT JOIN category c
              ON q.category_id = c.id
WHERE  q.non_text = 0
ORDER  BY Random()
LIMIT  1

--name: get_all_questions
SELECT c.title,
       c.comment,
       c.show_year,
       q.value,
       q.question,
       q.answer
FROM   question q
       LEFT JOIN category c
              ON q.category_id = c.id
WHERE  q.non_text = 0

--name: get_questions_like
SELECT c.title,
       c.comment,
       c.show_year,
       q.value,
       q.question,
       q.answer
FROM   question q
       LEFT JOIN category c
              ON q.category_id = c.id
WHERE  q.question LIKE '%' || ?1 || '%' OR
       q.answer LIKE '%' || ?1 || '%'

--name: create_category_table
CREATE TABLE IF NOT EXISTS category
  (
     id          INTEGER NOT NULL PRIMARY KEY,
     show_number INTEGER,
     show_year   INTEGER,
     title       TEXT,
     comment     TEXT
  ) 

--name: create_question_table
CREATE TABLE IF NOT EXISTS question
  (
     id          INTEGER NOT NULL PRIMARY KEY,
     category_id INTEGER,
     value       INTEGER,
     question    TEXT,
     answer      TEXT,
     non_text    INTEGER
  ) 

--name: create_player_table
CREATE TABLE IF NOT EXISTS player
  (
     id          INTEGER NOT NULL PRIMARY KEY,
     uid         TEXT,
     name        TEXT,
     score       INTEGER,
     correct     INTEGER,
     incorrect   INTEGER,
     platform    TEXT
  ) 

--name: create_attempt_table
CREATE TABLE IF NOT EXISTS attempt
  (
     id                INTEGER NOT NULL PRIMARY KEY,
     question_id       INTEGER,
     time              INTEGER,
     attempts          INTEGER,
     players           INTEGER,
     correct_player_id INTEGER
  )

--name: make_question_attempt
INSERT INTO attempt
  (
    question_id,
    time
  ) VALUES (
    ?,
    ?
  )

--name: get_player_id
SELECT id FROM player
WHERE uid = :uid
  AND platform = :platform

--name: update_question_attempt
UPDATE attempt
SET attempts = :attempts,
    players = :players,
    correct_player_id = :player_id
WHERE id = :id