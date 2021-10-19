import unittest
from unittest.mock import Mock

from ..trivia_core import TriviaCore

class TestTriviaCore(unittest.TestCase):

    def setUp(self):
        config = {
          "database_path": ":memory:",
          "admin_uid": "a",
          "min_matching_characters": 5,
          "scoreboard_schedule": [
          ]
        }

        self._trivia = TriviaCore(**config, platform='test')
        self._trivia._db.execute('test_add_categories', auto_commit=True)
        self._trivia._db.execute('test_add_questions', auto_commit=True)

    def test_question(self):
        f = Mock()
        self._trivia.on_post_question(f)
        f.assert_called_with({
            'winning_user': None,
            'winning_answer': None,
            'id': 1,
            'category': 'This is a category',
            'comment': 'This is a category comment',
            'year': 2000,
            'value': 200,
            'question': 'question',
            'answer': 'answer'
            })
        self._trivia.handle_message('a', 'qwerty', 'payload')
        f.reset_mock()
        f.assert_not_called()
        self._trivia.handle_message('a', 'answer', 'payload')
        f.assert_called_with({
            'winning_user': {
                'rank': 1,
                'uid': 'a',
                'score': 200,
                'correct': 1,
                'incorrect': 0,
                'percent': 100
                },
            'winning_answer': 'answer',
            'id': 1,
            'category': 'This is a category',
            'comment': 'This is a category comment',
            'year': 2000,
            'value': 200,
            'question': 'question',
            'answer': 'answer'
            })

if __name__ == '__main__':
    unittest.main()
