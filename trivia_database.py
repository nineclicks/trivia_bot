import re
import sqlite3
from time import time
from pathlib import Path
from threading import Lock


REG_QUERIES = r'(?i)^\s*--\s*name\s*:\s*(\S+)\s*\n([\S\s]+?)(?=--name|\Z)'
QUERIES_FILE = 'queries.sql'

class TriviaDatabase:

    def __init__(self, db_path):
        queries_path = Path(__file__).parent / QUERIES_FILE
        self._db = DatabaseHelper(db_path, queries_path)
        self._create_tables()

    def get_question(self):
        return self._db.select_one('get_random_question', as_map=True)

    def make_question_attempt(self):
        self._current_question = self.get_question()
        self._db.execute(
            'make_question_attempt',
            (self._current_question['id'], time()),
            auto_commit=True
        )
        self._current_question_attempt = self._db.last_row_id
        return self._current_question

    def update_question_attempt(self):
        pass

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

trivia = TriviaDatabase('j_questions.db')
print(trivia.get_question())