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
     complete_time     INTEGER,
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
    correct_player_id = :player_id,
    complete_time = :complete_time
WHERE time = (SELECT MAX(time) FROM attempt)

--name: get_last_question
SELECT q.id,
       c.title as category,
       c.comment as comment,
       c.show_year as year,
       q.value as value,
       q.question,
       q.answer
FROM attempt a
       LEFT JOIN question q
              on a.question_id = q.id
       LEFT JOIN category c
              ON q.category_id = c.id
WHERE  a.time = (SELECT MAX(time) FROM attempt)
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
    score,
    correct,
    incorrect,
    platform
  )
SELECT
  :uid,
  0,
  0,
  0,
  :platform
WHERE NOT EXISTS (SELECT 1 FROM player WHERE uid = :uid)

--name: answer_right
UPDATE player
SET score = (SELECT score + :value FROM player WHERE uid = :uid and platform = :platform)
  , correct = (SELECT correct + 1 FROM player WHERE uid = :uid and platform = :platform)
WHERE uid = :uid and platform = :platform

--name: answer_wrong
UPDATE player
SET incorrect = (SELECT incorrect + 1 FROM player WHERE uid = :uid and platform = :platform)
WHERE uid = :uid and platform = :platform

--name: get_scores
SELECT
  uid,
  score,
  correct,
  incorrect
FROM player
WHERE platform = ?
ORDER BY score DESC

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
            attempt a 
            ON p.id = a.correct_player_id 
         LEFT JOIN
            question q 
            ON a.question_id = q.id 
      WHERE
         a.complete_time >= :start_time
         AND (a.complete_time < :end_time OR :end_time IS NULL)
      GROUP BY
         p.uid
   )
WHERE
   uid = :uid
   OR :uid IS NULL;