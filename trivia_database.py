import re
import sqlite3
import logging
from time import time
from pathlib import Path
from threading import Lock
from fuzzywuzzy import fuzz

REG_QUERIES = r'(?i)^\s*--\s*name\s*:\s*(\S+)\s*\n([\S\s]+?)(?=--name|\Z)'
QUERIES_FILE = 'queries.sql'

class TriviaDatabase:

    def __init__(self, db_path, platform, matching):
        logging.info('Starting Trivia Database')
        self._matching = matching
        self._platform = platform
        queries_path = Path(__file__).parent / QUERIES_FILE
        self._db = DatabaseHelper(db_path, queries_path)
        self._create_tables()
        self.current_question = self.get_last_question()

    def get_question(self):
        return self._db.select_one('get_random_question', as_map=True)

    def get_last_question(self):
        return self._db.select_one('get_last_question', as_map=True)

    def check_answer(self, answer):
        #ratio = fuzz.token_sort_ratio(answer, self.current_question['answer'])
        ratio = fuzz.ratio(answer, self.current_question['answer'])

        if (len(answer) >= self._matching['character_count'] and
            answer.strip().lower() in self.current_question['answer'].lower()):
            logging.info('Correct answer ' + str(self._matching['character_count']) + ' consecutive characters')
            return True

        elif ratio >= self._matching['fuzzy_threshold']:
            logging.info('Correct answer ' + str(ratio) + r'% fuzzy match')
            return True

        return False

    def add_user(self, user):
        self._db.execute('add_player', {
            'uid': user,
            'platform': self._platform
        }, auto_commit=True)

    def user_wrong_answer(self, user):
        self._db.execute('answer_wrong', {
            'uid': user,
            'platform': self._platform,
        }, auto_commit=True)

    def user_right_answer(self, user, value):
        self._db.execute('answer_right', {
            'uid': user,
            'platform': self._platform,
            'value': value,
        }, auto_commit=True)

    def make_question_attempt(self):
        self.current_question = self.get_question()
        logging.info('New question id: ' + str(self.current_question['id']))
        self._db.execute(
            'make_question_attempt',
            (self.current_question['id'], int(time())),
            auto_commit=True
        )
        return self.current_question

    def get_player_score(self, uid):
        row = self._db.select_one('get_player_score', {
            'uid': uid,
            'platform': self._platform,
        })
        if row is None:
            return 0
        return row[0]

    def get_player_rank(self, uid):
        row = self._db.select_one('get_player_rank', {
            'uid': uid,
            'platform': self._platform,
        })
        if row is None:
            return 999
        return row[0]

    def get_scores(self):
        rows = self._db.select_iter('get_scores', (self._platform,), as_map=True)
        scores = []
        for row in rows:
            scores.append(row)
        return scores

    def update_question_attempt(self, attempts, players, correct_uid = None):
        logging.info('Question winner player id: ' + (str(correct_uid) or 'none'))
        params = {
            'attempts': attempts,
            'players': players,
            'player_id': None,
        }
        if correct_uid is not None:
            player_id = self._db.select_one(
                'get_player_id',
                {'uid': correct_uid, 'platform': self._platform},
                as_map=True)['id']

            params['player_id'] = player_id

        self._db.execute(
            'update_question_attempt',
            params,
            auto_commit=True
        )

    def _create_tables(self):
        table_queries = [
            'create_category_table',
            'create_question_table',
            'create_player_table',
            'create_attempt_table',
        ]

        for q in table_queries:
            self._db.execute(q)

        self._db.commit()

class DatabaseHelper:

    def __init__(self, db_path, queries_path):
        self._queries = self._load_queries(queries_path)
        self._lock = Lock()
        self._connection = sqlite3.connect(db_path, check_same_thread=False)

    def _do_execute(self, query_name, params = None):
        if params is None:
            params = ()

        cursor = self._connection.cursor()
        query = self._queries[query_name]
        cursor.execute(query, params)
        self.last_row_id = cursor.lastrowid

        return cursor

    def execute(self, query_name, params = None, auto_commit = False):
        with self._lock:
            self._do_execute(query_name, params)

            if auto_commit:
                self._connection.commit()

    def commit(self):
        with self._lock:
            self._connection.commit()
        
    def select_iter(self, query_name, params = None, as_map = False):
        with self._lock:
            cursor = self._do_execute(query_name, params)
            row = cursor.fetchone()

            while row is not None:
                if as_map:
                    row = self.row_as_map(cursor, row)

                yield row
                row = cursor.fetchone()
        
    def select_one(self, query_name, params = None, as_map = False):
        with self._lock:
            cursor = self._do_execute(query_name, params)
            row = cursor.fetchone()

            if as_map:
                row = self.row_as_map(cursor, row)

            return row

    @staticmethod
    def row_as_map(cursor, row):
        if row is None:
            return None
        return {k[0]:row[i] for i,k in enumerate(cursor.description)}

    @staticmethod
    def _load_queries(filename):
        queries = {}

        with open(filename, 'r') as fp:
            query_text = fp.read()

        matches = re.finditer(REG_QUERIES, query_text, flags = re.MULTILINE)

        for match in matches:
            name = match[1]
            query = match[2]
            queries[name] = query
        
        return queries
