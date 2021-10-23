from os import stat
import unittest
from datetime import datetime
import time
import logging
from unittest import mock
from unittest.mock import Mock, patch, ANY

from trivia_core import TriviaCore
import trivia_core

class TestTriviaCore(unittest.TestCase):

    def setUp(self):
        config = {
          "database_path": ":memory:",
          "admin_uid": "a",
          "min_matching_characters": 5,
          "scoreboard_schedule": [
          ],
          "scoreboard_show_incorrect": False,
          "scoreboard_show_percent": False
        }

        self._trivia = TriviaCore(**config, platform='test')
        queries = {'test_add_categories': """
                    INSERT INTO category (show_number, show_year, title, comment
                    ) VALUES (
                      1, 2000, 'This is a category', 'This is a category comment'
                    )""",

                    'test_add_questions': """
                    INSERT INTO question (
                      category_id, value, question, answer, non_text
                    ) VALUES (
                      (SELECT id FROM category LIMIT 1), 200, 'question', 'answer', 0
                    )"""}

        self._trivia._db._queries = {**self._trivia._db._queries, **queries}

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

    @staticmethod
    def parse_scoreboard(scoreboard_str:str):
        return [line.split() for line in scoreboard_str.strip().split('\n')[4:]]

    def test_missing_configs(self):
        """
        Trivia Core should complain and set defaults for some missing config options
        """
        config = {
          "database_path": ":memory:",
          "admin_uid": "a",
          "min_matching_characters": 5,
          "scoreboard_schedule": [
          ],
        }

        with self.assertLogs(level=logging.WARNING):
            self._trivia = TriviaCore(**config, platform='test')

        self.assertEqual(self._trivia._config['scoreboard_show_incorrect'], False)
        self.assertEqual(self._trivia._config['scoreboard_show_percent'], False)

    def test_no_question_handler(self):
        """
        Trivia Core should error if it gets messages before a question handler is set
        """
        with self.assertRaises(Exception):
            self._trivia.handle_message('b', 'blabla', 'payload')

    def test_pre_format(self):
        """
        Test the pre_format handler
        """
        self._trivia.on_pre_format(lambda x: f'```{x}```')
        mock_post_reply = Mock()
        self._trivia.on_post_reply(mock_post_reply)
        self._trivia.on_post_question(lambda *_, **__: None)
        self._trivia.handle_message('b', '!help', 'payload')
        message = mock_post_reply.call_args[0][0]
        self.assertEqual(message[:3], '```')
        self.assertEqual(message[-3:], '```')

    def test_get_display_name(self):
        """
        Test the get_display name handler
        """
        self._trivia.on_get_display_name(lambda x: x.upper())
        mock_post_reply = Mock()
        self._trivia.on_post_reply(mock_post_reply)
        self._trivia.on_post_question(lambda *_, **__: None)
        self._trivia.handle_message('a', 'answer', 'payload')
        self._trivia.handle_message('a', '!today', 'payload')
        message = mock_post_reply.call_args[0][0]
        username = message.strip().split('\n')[4].split()[1]
        self.assertEqual(username, 'A')

    def test_skip_scoreboard_if_no_scores(self):
        """
        Make sure no scores are posted if suppress_no_scores=True and there
        are no scores
        """
        mock_post_reply = Mock()
        self._trivia.on_post_reply(mock_post_reply)
        self._trivia.on_post_question(lambda *_, **__: None)
        self._trivia._show_scores(suppress_no_scores=True, message_payload='payload')
        mock_post_reply.assert_not_called()

    def test_scoreboard_no_payload(self):
        """
        When no message_payload is provided (like when run from a schedule)
        the scoreboard should be posted via post_message rather than post_reply
        """
        mock_post_reply = Mock()
        mock_post_message = Mock()
        self._trivia.on_post_reply(mock_post_reply)
        self._trivia.on_post_message(mock_post_message)
        self._trivia.on_post_question(lambda *_, **__: None)
        self._trivia._show_scores(suppress_no_scores=False)
        mock_post_reply.assert_not_called()
        mock_post_message.assert_called()

    def test_correct_answer_callback(self):
        """
        Test correct answer callback
        """
        self._trivia.on_get_display_name(lambda x: x.upper())
        mock_correct_callback = Mock()
        self._trivia.on_correct_answer(mock_correct_callback)
        self._trivia.on_post_question(lambda *_, **__: None)
        self._trivia.handle_message('a', 'ablabla', 'payload')
        mock_correct_callback.assert_not_called()
        self._trivia.handle_message('a', 'answer', 'payload')
        mock_correct_callback.assert_called()

    def test_nonesense(self):
        """
        Just ignore some nonsense input
        """
        nonsense = [
            'blabla',
            '!kfgdkfjkd',
            '!!!',
            '!!help',
            '`1`12l`129`j12///12`1\\\\',
            'This statement is false.',
        ]
        mock_post_reply = Mock()
        mock_post_message = Mock()
        self._trivia.on_post_reply(mock_post_reply)
        self._trivia.on_post_message(mock_post_message)
        self._trivia.on_post_question(lambda *_, **__: None)
        self._trivia.handle_message('b', 'blabla', 'payload')
        for word in nonsense:
            mock_post_reply.reset_mock()
            mock_post_message.reset_mock()
            self._trivia.handle_message('b', word, 'payload')
            mock_post_reply.assert_not_called()
            mock_post_message.assert_not_called()

    def test_help(self):
        """
        Test the help message
        """
        mock_post_reply = Mock()
        self._trivia.on_post_reply(mock_post_reply)
        self._trivia.handle_message('b', '!help', 'payload')
        mock_post_reply.assert_called()
        help = mock_post_reply.call_args[0][0]
        self.assertIn('!new', help)
        self.assertIn('!help', help)

    def test_uptime(self):
        """
        Test uptime message, non-admin shouldn't be able to
        """
        mock_post_reply = Mock()
        self._trivia.on_post_reply(mock_post_reply)
        self._trivia.handle_message('b', '!uptime', 'payload')
        # b is not admin
        mock_post_reply.assert_not_called()

        self._trivia.handle_message('a', '!uptime', 'payload')
        mock_post_reply.assert_called()
        uptime = mock_post_reply.call_args[0][0]
        self.assertEqual(len(uptime.split(':')), 3)

    def test_answer_matching(self):
        correct_answers = (
            ('test', 'test'),
            ('python', 'python'),
            ('five', '5'),
            ('cdefg', 'abcdefghi'),
            ('ONEtwoTHREE', 'onetwothree'),
            ('one two three', 'onetwothree'),
            ('Thom Yorke', 'Thom (Yorke)'),
            ('one & two', 'one and two'),
            ('pie', 'a pie'),
            ('act', 'an act'),
            ('cat', 'the cat'),
            ('cliche', 'cliché'),
            ('10%', '10 percent'),
            (' abcde ', 'abcde'),
        )

        incorrect_answers = (
            ('one', 'two'),
            ('1', '2'),
            ('1950s', '1960s'),
            ('two', 'one two three'),
            ('abcd', 'abcde'),
            ('ab\ncde', 'abcde'),
        )

        for answer in correct_answers:
            self.assertTrue(self._trivia._do_check_answer(*answer, 5))

        for answer in incorrect_answers:
            self.assertFalse(self._trivia._do_check_answer(*answer, 5))

    @patch('trivia_core.time')
    @patch('trivia_core.datetime')
    def test_question(self, mock_datetime, mock_time):
        """
        Test a bunch of scoreboard stuff.
        This is the most precarious part of this code to be honest.
        """
        self._trivia._config['scoreboard_show_incorrect'] = True
        self._trivia._config['scoreboard_show_percent'] = True
        operations = (
            ('setdate', (2000, 1, 2)),
            ('wronganswer', 'a'),
            ('q_no_post', None),
            ('wronganswer', 'b'),
            ('q_no_post', None),
            ('answer', 'a'),
            ('q_post', {'uid': 'a', 'rank': 1}),
            ('answer', 'a'),
            ('q_post', {'uid': 'a', 'rank': 1}),
            ('answer', 'a'),
            ('q_post', {'uid': 'a', 'rank': 1}),
            ('answer', 'b'),
            ('q_post', {'uid': 'b', 'rank': 2}),
            ('answer', 'b'),
            ('q_post', {'uid': 'b', 'rank': 2}),
            ('answer', 'c'),
            ('q_post', {'uid': 'c', 'rank': 3}),
            ('scoreboard_cmd', ('!today', 'Sunday January 02 2000', (
                ('a', 3, 0), # "a" gets it wrong then right so not in incorrect
                ('b', 2, 1),
                ('c', 1, 0),
            ))),

            ('setdate', (2000, 1, 3)),
            ('scoreboard_cmd', ('!yesterday', 'Sunday January 02 2000', (
                ('a', 3, 0),
                ('b', 2, 1),
                ('c', 1, 0),
            ))),
            ('answer', 'b'),
            ('q_post', {'uid': 'b', 'rank': 1}),
            ('answer', 'b'),
            ('q_post', {'uid': 'b', 'rank': 1}),
            ('scoreboard_cmd', ('!week', 'week starting Sunday January 02 2000', (
                ('b', 4, 1),
                ('a', 3, 0),
                ('c', 1, 0),
            ))),
            ('scoreboard_cmd', ('!month', 'January 2000', (
                ('b', 4, 1),
                ('a', 3, 0),
                ('c', 1, 0),
            ))),
            ('scoreboard_cmd', ('!year', '2000', (
                ('b', 4, 1),
                ('a', 3, 0),
                ('c', 1, 0),
            ))),
            ('scoreboard_cmd', ('!alltime', 'Alltime Scores', (
                ('b', 4, 1),
                ('a', 3, 0),
                ('c', 1, 0),
            ))),

            ('setdate', (2000, 2, 1)),
            ('answer', 'c'),
            ('answer', 'c'),
            ('wronganswer', 'a'),
            ('wronganswer', 'a'),
            ('wronganswer', 'a'), # only count 1 wrong per question
            ('answer', 'c'),
            ('answer', 'c'),
            ('wronganswer', 'c'),
            ('answer', 'b'),
            ('answer', 'b'),
            ('wronganswer', 'c'),
            ('answer', 'a'),
            ('scoreboard_cmd', ('!today', 'Tuesday February 01 2000', (
                ('c', 4, 2),
                ('b', 2, 0),
                ('a', 1, 1),
            ))),
            ('scoreboard_cmd', ('!yesterday', 'Monday January 31 2000', (
            ))),
            ('scoreboard_cmd', ('!month', 'February 2000', (
                ('c', 4, 2),
                ('b', 2, 0),
                ('a', 1, 1),
            ))),
            ('scoreboard_cmd', ('!alltime', 'Alltime Scores', (
                ('b', 6, 1),
                ('c', 5, 2),
                ('a', 4, 1),
            ))),
            ('answer', 'c'),
            ('q_post', {'uid': 'c', 'rank': 1}),
            ('answer', 'b'),
            ('q_post', {'uid': 'b', 'rank': 2}),
            ('answer', 'a'),
            ('q_post', {'uid': 'a', 'rank': 3}),
            ('answer', 'a'),
            ('q_post', {'uid': 'a', 'rank': 2}),
            ('answer', 'a'),
            ('q_post', {'uid': 'a', 'rank': 2}),
            ('answer', 'a'),
            ('q_post', {'uid': 'a', 'rank': 1}),
            ('answer', 'a'),
            ('q_post', {'uid': 'a', 'rank': 1}),
            ('answer', 'd'),
            ('q_post', {'uid': 'd', 'rank': 4}),
            ('scoreboard_cmd', ('!today', 'Tuesday February 01 2000', (
                ('a', 6, 1),
                ('c', 5, 2),
                ('b', 3, 0),
                ('d', 1, 0),
            ))),



            ('setdate', (2001, 1, 1)),
            ('wronganswer', 'z'),
            ('answer', 'a'),
            ('answer', 'a'),
            ('answer', 'a'),
            ('answer', 'b'),
            ('answer', 'b'),
            ('answer', 'c'),
            ('scoreboard_cmd', ('!today', 'Monday January 01 2001', (
                ('a', 3, 0),
                ('b', 2, 0),
                ('c', 1, 0),
                ('z', 0, 1),
            ))),
            ('scoreboard_cmd', ('!week', 'week starting Sunday December 31 2000', (
                ('a', 3, 0),
                ('b', 2, 0),
                ('c', 1, 0),
                ('z', 0, 1),
            ))),
            ('scoreboard_cmd', ('!month', 'January 2001', (
                ('a', 3, 0),
                ('b', 2, 0),
                ('c', 1, 0),
                ('z', 0, 1),
            ))),
            ('scoreboard_cmd', ('!year', '2001', (
                ('a', 3, 0),
                ('b', 2, 0),
                ('c', 1, 0),
                ('z', 0, 1),
            ))),
            ('scoreboard_cmd', ('!alltime', 'Alltime Scores', (
                ('a', 12, 1),
                ('b', 9, 1),
                ('c', 7, 2),
                ('d', 1, 0),
                ('z', 0, 1),
            ))),
            ('scoreboard', ({'days_ago': 0}, 'Monday January 01 2001', (
                ('a', 3, 0),
                ('b', 2, 0),
                ('c', 1, 0),
                ('z', 0, 1),
            ))),
            ('scoreboard', ({'weeks_ago': 1, 'suppress_no_scores': True}, 'week starting Sunday December 24 2000', (
            ))),
            ('scoreboard', ({'weeks_ago': 1}, 'week starting Sunday December 24 2000', (
            ))),
            ('scoreboard', ({'years_ago': 1}, '2000', (
                ('a', 9, 1),
                ('b', 7, 1),
                ('c', 6, 2),
                ('d', 1, 0),
            ))),
        )
        mock_ask_question = Mock()
        mock_post_reply = Mock()
        mock_post_message = Mock()

        # auto new question on new db
        self._trivia.on_post_reply(mock_post_reply)
        self._trivia.on_post_message(mock_post_message)
        self._trivia.on_post_question(mock_ask_question)
        mock_ask_question.assert_called_with(self.question_template(winning_user=None, question='question'))
        mock_ask_question.reset_mock()


        for op, dat in operations:
            if op == 'setdate':
                dt = datetime(*dat, 12, 30)
                mock_datetime.today.return_value = dt
                mock_time.side_effect = range(int(dt.timestamp()),int(dt.timestamp()) + 10000)

            elif op == 'answer':
                self._trivia.handle_message(dat, 'answer', 'payload')

            elif op == 'wronganswer':
                self._trivia.handle_message(dat, 'qwerty', 'payload')

            elif op == 'q_post':
                with self.subTest(f'Question asked with {str(dat)}'):
                    mock_ask_question.assert_called_with(self.question_template(**dat))

            elif op == 'q_no_post':
                with self.subTest('Question not asked'):
                    mock_ask_question.assert_not_called()

            elif op in ('scoreboard_cmd', 'scoreboard'):
                with self.subTest('Test scoreboard result'):
                    cmd, date_str, exp_scores = dat

                    mock_post_message.reset_mock()
                    mock_post_reply.reset_mock()

                    if op == 'scoreboard_cmd':
                        self._trivia.handle_message('a', cmd, 'payload')

                    else:
                        self._trivia._show_scores(**cmd)

                    if op == 'scoreboard' and cmd.get('suppress_no_scores', False) == True:
                        mock_post_message.assert_not_called()
                        mock_post_reply.assert_not_called()

                        continue

                    if op == 'scoreboard_cmd' or cmd.get('message_payload') is not None:
                        scoreboard = mock_post_reply.call_args[0][0]
                    else:
                        scoreboard = mock_post_message.call_args[0][0]

                    self.assertIn(scoreboard.split('\n')[0], (
                        f'Scoreboard for {date_str}',
                        date_str # Alltime Scores case
                        ))
                    scores = self.parse_scoreboard(scoreboard)
                    self.assertEqual(len(scores), len(exp_scores))
                    for i, exp_score in enumerate(exp_scores):
                        self.assertEqual(scores[i], [
                            str(i+1),
                            exp_score[0],
                            f'{int(exp_score[1]) * 200:,}',
                            str(exp_score[1]),
                            str(exp_score[2]),
                            str(exp_score[1] * 100 // (exp_score[1] + exp_score[2]))
                            ])

if __name__ == '__main__':
    unittest.main()
