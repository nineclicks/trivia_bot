import unittest
from datetime import datetime
from unittest.mock import Mock, patch, ANY

import trivia_core
from trivia_core import TriviaCore

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

    @staticmethod
    def question_template(rank = ANY, uid=ANY, score=ANY, correct=ANY, incorrect=ANY, percent=ANY, **kwargs):
        question_template = {
                'winning_user': {
                    'rank': rank,
                    'uid': uid,
                    'score': score,
                    'correct': correct,
                    'incorrect': incorrect,
                    'percent': percent
                    },
                'winning_answer': ANY,
                'id': ANY,
                'category': ANY,
                'comment': ANY,
                'year': ANY,
                'value': ANY,
                'question': ANY,
                'answer': ANY
                }
        return {**question_template, **kwargs}


    def test_question(self):
        with patch('trivia_core.datetime') as mock_datetime:
            mock_datetime.today.return_value = datetime(2020, 1, 1, 12, 30)
            f = Mock()
            self._trivia.on_post_question(f)
            f.assert_called_with(self.question_template(winning_user=None, question='question'))
            self._trivia.handle_message('a', 'qwerty', 'payload')
            f.reset_mock()
            f.assert_not_called()
            self._trivia.handle_message('a', 'answer', 'payload')
            f.assert_called_with(self.question_template(uid='a', rank=1, winning_answer='answer'))

if __name__ == '__main__':
    unittest.main()
