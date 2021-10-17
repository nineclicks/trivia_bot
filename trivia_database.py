"""
Module for TriviaDatabase class
"""

import re
import sqlite3
from pathlib import Path
from threading import Lock
REG_QUERIES = r'(?i)^\s*--\s*name\s*:\s*(\S+)\s*\n([\S\s]+?)(?=--name|\Z)'
QUERIES_FILE = (Path(__file__).parent / 'queries.sql').resolve()

class TriviaDatabase:
    """
    Trivia database components
    """

    def __init__(self, db_path):
        self._queries = self._load_queries(QUERIES_FILE)
        self._lock = Lock()
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        for query in self._queries:
            if query.startswith('create_') and query.endswith('_table'):
                self.execute(query, auto_commit = True)

    def _do_execute(self, query_name, params = None):
        if params is None:
            params = ()

        cursor = self._connection.cursor()
        query = self._queries[query_name]
        cursor.execute(query, params)

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
                    row = self._row_as_map(cursor, row)

                yield row
                row = cursor.fetchone()

    def select_one(self, query_name, params = None, as_map = False):
        with self._lock:
            cursor = self._do_execute(query_name, params)
            row = cursor.fetchone()

            if as_map:
                row = self._row_as_map(cursor, row)

            return row

    @staticmethod
    def _row_as_map(cursor, row):
        if row is None:
            return None
        return {k[0]:row[i] for i,k in enumerate(cursor.description)}

    @staticmethod
    def _load_queries(filename):
        queries = {}

        with open(filename, 'r', encoding='utf-8') as file_pointer:
            query_text = file_pointer.read()

        matches = re.finditer(REG_QUERIES, query_text, flags = re.MULTILINE)

        for match in matches:
            name = match[1]
            query = match[2]
            queries[name] = query

        return queries
