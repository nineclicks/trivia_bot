"""
Module for TriviaCore class
"""

import os
import re
import signal
import logging
from time import time, strftime, localtime
from datetime import datetime, timedelta
from threading import Lock

import unidecode
from tabulate import tabulate
from num2words import num2words
from apscheduler.schedulers.background import BackgroundScheduler

from .trivia_database import TriviaDatabase

SUGGESTED_CONFIGS = [
        ('admin_uid', ''),
        ('min_matching_characters', 5),
        ('platform', ''),
        ('scoreboard_show_incorrect', False),
        ('scoreboard_show_percent', False),
        ('scoreboard_schedule', []),
        ]

class TriviaCore:
    """
    Core trivia components
    """
    # pylint: disable=too-many-instance-attributes

    def __init__(self, database_path, **kwargs):
        logging.info('Starting Trivia Core')
        self._config = kwargs
        self._check_config()

        self._lock = Lock()
        self._starttime = time()
        self._attempts = []
        self._post_question_handler = lambda *_, **__: None
        self._post_message_handler = lambda *_, **__: None
        self._post_reply_handler = lambda *_, **__: None
        self._pre_format_handler = lambda x: x
        self._get_display_name_handler = lambda x: x
        self._correct_answer_handler = lambda *_, **__: None
        self._on_error_handler = lambda *_, **__: None
        self._db = TriviaDatabase(database_path)
        self._command_prefix = '!'
        self._current_question = self._get_last_question()
        self._create_scoreboard_schedule(kwargs['scoreboard_schedule'])

    def error(self, message_payload, text):
        self._on_error_handler(message_payload=message_payload, text=text)

    def handle_message(self, uid:str, text:str, message_payload):
        """
        Handle incoming answers and commands from users

        Arguments:
            uid (str): Message user's uid
            text (str): Message user's text
            message_payload (any): Message payload data for interacting with
                                   the given message
        """

        with self._lock:
            if text.startswith(self._command_prefix):
                self._handle_command(uid, text[1:], message_payload)

            else:
                if self._current_question is None:
                    raise ValueError('There is no current question. Have you set your @on_post_question handler?')
                self._attempt_answer(uid, text, message_payload)

    def on_pre_format(self, func):
        """Decorate your preformatted text handler function.

        Decorated function shall accept arguments:
            message (str)

        And return
            str: The message with block preformatting
        """

        self._pre_format_handler = func

        return func

    def on_post_question(self, func):
        """Decorate your post question handler function.

        Decorated function shall accept arguments:
            question (dict):
                winning_user (dict or None):
                    rank (int): Winner's rank for the day
                    uid (str): Winner's uid
                    score (int): Winner's score for the day
                    correct (int): Winner's number of correct for the day
                winning_answer (str): Answer for the previoud question
                category (str): Category for the new question
                comment (str): Comment for the new question
                year (int): Year of the new question
                value (int): Point value of the new question
                question (str): The new question text
                answer (str): The new question answer
        """

        self._post_question_handler = func

        if self._current_question is None:
            self._new_question()

        return func

    def on_post_message(self, func):
        """Decorate your post message handler function.

        Decorated function shall accept arguments:
            message (str): Message to post to trivia channel
        """

        self._post_message_handler = func

        return func

    def on_post_reply(self, func):
        """Decorate your post reply handler function.

        This function will be called when the admin messages the bot outside of
        the trivia channel. Use the message_payload to know where to reply.

        Decorated function shall accept arguments:
            message (str): Message to post to trivia channel
            message_payload (any): Same message_payload passed in to handle_message()
        """

        self._post_reply_handler = func

        return func

    def on_error(self, func):
        """Decorate your error handler function.

        This function will be called when there is a problem with a command
        Use the message_payload to know where to reply.

        Decorated function shall accept arguments:
            message_payload (any): Same message_payload passed in to handle_message()
            text (str): The text of the error.
        """

        self._on_error_handler = func

    def on_get_display_name(self, func):
        """Decorate your get display name handler function.

        Decorated function shall accept arguments:
            uid (str): User's uid for which to get a display name

        Decorated function shall return:
            str: The display name of the given uid
        """

        self._get_display_name_handler = func

        return func

    def on_correct_answer(self, func):
        """Decorate your correct answer handler function.

        Use this decorator for any extra actions taken with correct answer such
        as an emoji reaction.

        Decorated function shall accept arguments:
            message_payload (any): Same message_payload passed in to handle_message()
            question (dict):
                winning_user (dict or None):
                    rank (int): Winner's rank for the day
                    uid (str): Winner's uid
                    score (int): Winner's score for the day
                    correct (int): Winner's number of correct for the day
                winning_answer (str): Answer for the previoud question
                category (str): Category for the new question
                comment (str): Comment for the new question
                year (int): Year of the new question
                value (int): Point value of the new question
                question (str): The new question text
                answer (str): The new question answer
        """

        self._correct_answer_handler = func

        return func

    def _check_config(self):
        for suggested in SUGGESTED_CONFIGS:
            key = suggested[0]
            default = suggested[1]
            if key not in self._config:
                logging.warning(
                        '%s not supplied to TriviaCore, defaulting to %s',
                        key,
                        repr(default)
                        )
                self._config[key] = default

    def _create_scoreboard_schedule(self, schedules):
        self._sched = BackgroundScheduler()
        self._sched.start()

        for schedule in schedules:
            self._job = self._sched.add_job(
                self._show_scores,
                'cron',
                **schedule['time'],
                kwargs={**schedule['for'], 'suppress_no_scores': True},
                replace_existing=False)

    def _get_new_question(self):
        """
        Select a random question from the database
        """

        return self._db.select_one('get_random_question', as_map=True)

    def _get_last_question(self):
        """
        Restore the last unanswered question
        """

        return self._db.select_one('get_last_question', as_map=True)

    def _new_question(self, winning_user=None):
        if self._current_question:
            winning_answer = self._current_question['answer']
        else:
            winning_answer = None

        self._attempts = []
        question = self._create_question_round()
        self._post_question_handler({
            'winning_user': winning_user,
            'winning_answer': winning_answer,
            **question
            })

    def _attempt_answer(self, uid:str, answer:str, message_payload):
        self._attempts.append(uid)

        if self._check_answer(answer):
            self._correct_answer_handler(message_payload, self._current_question)

            self._complete_question_round(winning_uid=uid)

    def _handle_command(self, uid, text, message_payload):
        for command in self._commands():
            if text in command[0]:
                command[2](uid=uid, text=text, message_payload=message_payload)
                break

    def _check_answer(self, answer):
        """
        Check an answer against the current question
        """

        correct_answer = self._current_question['answer']
        return self._do_check_answer(
                answer,
                correct_answer,
                self._config.get('min_matching_characters', 5)
                )

    def _player_attempt(self, uid, attempts, correct):
        self._db.execute('player_attempt', {
            'uid': uid,
            'attempts': int(attempts),
            'correct': int(correct)
            }, auto_commit=True)

    def _command_next(self, message_payload):
        start_time = self._db.select_one('get_current_round_start_time')[0]
        round_age = int(time() - start_time)
        min_seconds = self._config.get('min_seconds_before_new', 0)
        seconds_left = min_seconds - round_age


        if seconds_left > 0:
            self.error(message_payload, f'Please wait {seconds_left} seconds to do that.')

        else:
            self._complete_question_round(None)

    def _complete_question_round(self, winning_uid):
        logging.info('Question winner player id: %s', winning_uid or 'none')

        for attempt_user in set(self._attempts):
            self._add_user(attempt_user)
            self._player_attempt(
                    attempt_user,
                    self._attempts.count(attempt_user),
                    attempt_user == winning_uid
                    )

        self._update_question_round_table()

        winning_user = None

        if winning_uid:
            stats = self._get_player_stats_timeframe(winning_uid, self._timestamp_midnight())
            winning_user = next(stats, None)
            stats = None # This is crutial to release the generator and therefore the db lock

        self._new_question(winning_user)

    def _commands(self):
        return (
            (
                ['exit'],
                None, # Won't show in help message
                self._command_exit
            ),
            (
                ['uptime'],
                None, # Won't show in help message
                self._command_uptime
            ),
            (
                ['new', 'trivia new'],
                'Skip to the next question',
                lambda *_, message_payload=None, **__: self._command_next(message_payload=message_payload)
            ),
            (
                ['alltime', 'score', 'scores'],
                'Scores for all time',
                lambda *_, message_payload=None, **__: self._show_scores(days_ago=None, suppress_no_scores=False, message_payload=message_payload)
            ),
            (
                ['yesterday'],
                'Scores for yesterday',
                lambda *_, message_payload=None, **__: self._show_scores(days_ago=1, suppress_no_scores=False, message_payload=message_payload)
            ),
            (
                ['today'],
                'Scores for today',
                lambda *_, message_payload=None, **__: self._show_scores(days_ago=0, suppress_no_scores=False, message_payload=message_payload)
            ),
            (
                ['week'],
                'Scores for this week',
                lambda *_, message_payload=None, **__: self._show_scores(weeks_ago=0, suppress_no_scores=False, message_payload=message_payload)
            ),
            (
                ['month'],
                'Scores for this month',
                lambda *_, message_payload=None, **__: self._show_scores(months_ago=0, suppress_no_scores=False, message_payload=message_payload)
            ),
            (
                ['year'],
                'Scores for this year',
                lambda *_, message_payload=None, **__: self._show_scores(years_ago=0, suppress_no_scores=False, message_payload=message_payload)
            ),
            (
                ['help'],
                'Show this help info',
                self._command_help
            ),
        )

    def _add_user(self, uid):
        self._db.execute('add_player', {
            'uid': uid,
            'platform': self._config.get('platform')
        }, auto_commit=True)

    def _create_question_round(self):
        self._current_question = self._get_new_question()
        logging.info('New question id: %s', self._current_question['id'])
        self._db.execute(
            'create_question_round',
            (self._current_question['id'], int(time())),
            auto_commit=True
        )
        return self._current_question

    def _get_player_stats_timeframe(self, uid, start_time, end_time=None):
        rows = self._db.select_iter('get_timeframe_scores', {
            'uid': uid,
            'start_time': start_time,
            'end_time': end_time,
        }, as_map=True)

        for row in rows:
            yield row

    def _update_question_round_table(self):
        params = {
            'complete_time': int(time()),
        }

        self._db.execute(
            'update_question_round',
            params,
            auto_commit=True
        )

    def _command_exit(self, *_, message_payload, **kwargs):
        if kwargs.get('uid') == self._config.get('admin_uid'):
            self._post_reply_handler('ok bye', message_payload=message_payload)
            self._do_exit()

    def _command_help(self, *_, message_payload, **__):
        template = '{}{:<20}{}'
        fmt = lambda x: template.format(self._command_prefix, x[0][0], x[1])
        c_list = [fmt(x) for x in self._commands() if x[1] is not None]
        commands = '\n'.join(c_list)
        formatted = self._pre_format_handler(commands)
        self._post_reply_handler(formatted, message_payload=message_payload)

    def _command_uptime(self, *_, message_payload, **kwargs):
        if kwargs.get('uid') == self._config.get('admin_uid'):
            uptime = int(time()) - int(self._starttime)
            uptime_str = str(timedelta(seconds=uptime))
            format_str = f'{uptime_str:0>8}'
            self._post_reply_handler(format_str, message_payload=message_payload)

    def _show_scores(self, suppress_no_scores=False, message_payload=None, **kwargs):
        kwargs = {k:v for k,v in kwargs.items() if v is not None}

        if len(kwargs) == 0:
            start = 0
            end = None
            title = 'Alltime Scores'
        else:
            start = self._timestamp_midnight(**kwargs)

            # subtract one from whichever of days_ago, weeks_ago, etc is set
            kwargs_minus_one = {k:v-1 for k,v in kwargs.items() if isinstance(v, int)}
            end = self._timestamp_midnight(**kwargs_minus_one)

            title = f'Scoreboard for {self._ftime(start, kwargs)}'

        scores = list(self._get_player_stats_timeframe(None, start, end))

        if suppress_no_scores and len(scores) == 0:
            return

        for score in scores:
            # Get the current display name from slack, limit to 32 chars
            score['name'] = self._get_display_name_handler(score['uid'])[:32]

        title2 = '=' * len(title)
        scoreboard = self._format_scoreboard(scores)
        scoreboard_pre = f'{title}\n{title2}\n{scoreboard}'
        formatted = self._pre_format_handler(scoreboard_pre)
        if message_payload:
            self._post_reply_handler(formatted, message_payload)
        else:
            self._post_message_handler(formatted)

    @staticmethod
    def _do_exit():
        os.kill(os.getpid(), signal.SIGTERM)

    @staticmethod
    def _timestamp_midnight(days_ago=None, weeks_ago=None, months_ago=None, years_ago=None):
        day_start = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

        if days_ago is not None:
            day_start = day_start - timedelta(days=days_ago)

        elif weeks_ago is not None:
            day_of_week = (datetime.today().weekday() + 1) % 7
            day_start = day_start - timedelta(day_of_week)
            day_start = day_start - timedelta(weeks_ago * 7)

        elif months_ago is not None:
            day_start = day_start.replace(day=1)
            month = day_start.month - months_ago
            year = day_start.year

            while month < 1:
                month += 12
                year -= 1

            while month > 12:
                month -= 12
                year += 1

            day_start = day_start.replace(year=year, month=month)

        elif years_ago is not None:
            year = day_start.year - years_ago
            day_start = day_start.replace(year=year, month=1, day=1)

        return int(day_start.timestamp())

    @staticmethod
    def _ftime(timestamp, time_ago):
        format_str = ''
        formats = {
                'days_ago': '%A %B %d %Y',
                'weeks_ago': 'week starting %A %B %d %Y',
                'months_ago': '%B %Y',
                'years_ago': '%Y',
                }

        for k,v in time_ago.items():
            if v is not None:
                format_str = formats[k]

        return strftime(format_str,localtime(int(timestamp)))

    def _format_scoreboard(self, scores):
        cols = [
            ('rank', lambda x: x),
            ('name', lambda x: x),
            ('score', lambda x: f'{x:,}'),
            ('correct', lambda x: x),
        ]

        if self._config.get('scoreboard_show_incorrect', False):
            cols.append(('incorrect', lambda x: x))

        if self._config.get('scoreboard_show_percent', False):
            cols.append(('percent', lambda x: x))

        return tabulate([{col: fn(x[col]) for col, fn in cols} for x in scores], headers='keys')

    @staticmethod
    def _answer_variants(answer):
        answer_filters = [
            lambda x: [unidecode.unidecode(x)] if unidecode.unidecode(x) != x else [],
            lambda x: [re.sub(r'[0-9]+(?:[\.,][0-9]+)?', lambda y: num2words(y.group(0)), x)],
            lambda x: [x.replace(a, b) for a,b in [['&', 'and'],['%', 'percent']] if a in x],
            lambda x: [x[len(a):] for a in ['a ', 'an ', 'the '] if x.startswith(a)],
            lambda x: [''.join([a for a in x if a not in ' '])],
            lambda x: [''.join([a for a in x if a not in '\'().,"-'])],
        ]

        possible_answers = [answer.lower()]
        for answer_filter in answer_filters:
            for possible_answer in possible_answers:
                try:
                    possible_answers = list(set(
                        [*possible_answers, *answer_filter(possible_answer)]
                        ))
                except Exception as ex:
                    logging.exception(ex)

        return possible_answers

    @staticmethod
    def _do_check_answer(answer, correct_answer, match_character_count):
        correct_answer_variations = TriviaCore._answer_variants(correct_answer)
        given_answer_variations = TriviaCore._answer_variants(answer)

        for correct_answer_variation in correct_answer_variations:
            for given_answer_variation in given_answer_variations:
                min_match_len = min(match_character_count, len(correct_answer_variation))
                if (len(given_answer_variation.strip(' ')) >= min_match_len and
                    given_answer_variation.strip() in correct_answer_variation):
                    return True

        return False
