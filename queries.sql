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
     platform    TEXT
  ) 

--name: create_question_round_table
CREATE TABLE IF NOT EXISTS question_round
  (
     id                INTEGER NOT NULL PRIMARY KEY,
     question_id       INTEGER,
     time              INTEGER,
     complete_time     INTEGER,
     correct_player_id INTEGER
  )

--name: create_attempt_table
CREATE TABLE IF NOT EXISTS attempt
  (
     id                INTEGER NOT NULL PRIMARY KEY,
     question_round_id INTEGER,
     player_id         INTEGER,
     attempts          INTEGER,
     correct           INTEGER
  )

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

--name: create_question_round
INSERT INTO question_round
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

--name: update_question_round
UPDATE question_round
SET correct_player_id = :player_id,
    complete_time = :complete_time
WHERE time = (SELECT MAX(time) FROM question_round)

--name: get_last_question
SELECT q.id,
       c.title as category,
       c.comment as comment,
       c.show_year as year,
       q.value as value,
       q.question,
       q.answer
FROM question_round a
       LEFT JOIN question q
              on a.question_id = q.id
       LEFT JOIN category c
              ON q.category_id = c.id
WHERE  a.time = (SELECT MAX(time) FROM question_round)
LIMIT  1

--name: get_player_score
SELECT score FROM player
WHERE uid = :uid
  AND platform = :platform

--name: get_player_rank
SELECT rank FROM (SELECT uid, RANK () OVER (ORDER BY score DESC ) rank FROM player WHERE platform = :platform)
WHERE uid = :uid

--name: add_player
INSERT INTO player
  (
    uid,
    platform
  )
SELECT
  :uid,
  :platform
WHERE NOT EXISTS (SELECT 1 FROM player WHERE uid = :uid)

--name: player_attempt
INSERT INTO attempt
(
  question_round_id,
  player_id,
  attempts,
  correct
) VALUES (
  (SELECT a.id FROM question_round a WHERE a.time = (SELECT MAX(b.time) FROM question_round b)),
  (SELECT id FROM player WHERE uid = :uid),
  :attempts,
  :correct
)

--name: get_timeframe_scores
SELECT
   rank, uid, score, correct
FROM
   (
      SELECT
         RANK () OVER (
      ORDER BY
         SUM(q.Value) DESC) rank,
         p.uid uid,
         SUM(q.value) score,
         COUNT(q.value) correct 
      FROM
         player p 
         LEFT JOIN
            question_round r 
            ON p.id = r.correct_player_id 
         LEFT JOIN
            question q 
            ON r.question_id = q.id 
      WHERE
         r.complete_time >= :start_time
         AND (r.complete_time < :end_time OR :end_time IS NULL)
      GROUP BY
         p.uid
   )
WHERE
   uid = :uid
   OR :uid IS NULL;
