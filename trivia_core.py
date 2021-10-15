import re
import logging
from time import time
from typing import Callable

import unidecode
from num2words import num2words

from trivia_database import TriviaDatabase

class TriviaCore:

    def __init__(self, admin_uid, db_path, platform, matching):
        logging.info('Starting Trivia Database')
        self._attempts = []
        self._post_question_handler = lambda: None
        self._post_message_handler = lambda: None
        self._matching = matching
        self._platform = platform
        self._db = TriviaDatabase(db_path)
        self.current_question = self._get_last_question()

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

    def _new_question(self, winning_uid=None):
        if self.current_question:
            winning_answer = self.current_question['answer']
        else:
            winning_answer = None

        self._attempts = []
        question = self._create_question_attempt()
        self._post_question_handler(winning_uid = winning_uid, winning_answer = winning_answer, **question)

    def attempt_answer(self, uid:str, answer:str, correct_callback:Callable=None):
        """A user attempts to answer a question

        Args:
            uid (str): The user's uid
            answer (str): The user's uid
            correct_callback (Callable, optional): Callback function to run if this attempt is correct.
        """
        self._attempts.append(uid)

        if self._check_answer(answer):
            if correct_callback:
                correct_callback()

            self._update_attempt(uid)
            self._new_question(uid)

    def handle_command(self, uid, text, callback):
        for command in self.commands():
            if text in command[0]:
                command[2](uid=uid, text=text, callback=callback)
                break

    def _check_answer(self, answer):
        """
        Check an answer against the current question
        """

        correct_answer = self.current_question['answer']
        return self._do_check_answer(answer, correct_answer, self._matching['character_count'])

    def _update_attempt(self, winning_uid):
        attempt_users = set(self._attempts)
        for attempt_user in attempt_users:
            self._add_user(attempt_user)
            if winning_uid != attempt_user:
                self._user_wrong_answer(attempt_user)
            else:
                self._user_right_answer(attempt_user, self.current_question['value'])

        self._update_question_attempt(
            attempts=len(self._attempts),
            players=len(attempt_users),
            correct_uid=winning_uid,
        )

        #message = '{}: *{}*'.format('Correct' if winning_uid is not None else 'Answer', self._trivia.current_question['answer'])
        #TODO send message
        #if winning_uid is not None:
        #    status = next(self._trivia.get_player_stats_timeframe(winning_uid, self.timestamp_midnight()), None) # TODO deal with None case
        #    score = status['score']
        #    rank = status['rank']
        #    message += ' -- {} (today: {:,} #{})'.format(self.get_username(winning_uid), score, rank)

    def post_question(self, fn):
        """Decorate you post question handler function.
        """
        self._post_question_handler = fn

        if self.current_question is None:
            self._new_question()

        return fn

    def post_message(self, fn):
        """Decorate you post message handler function.
        """
        self._post_message_handler = fn

        return fn

    def commands(self):
        return (
            (['exit'], None, self.exit),
            (['uptime'], None, self.uptime),
            (['new', 'trivia new'], 'Skip to the next question', lambda *_, **__: self._update_attempt(None, None)),
            (['alltime', 'score', 'scores'], 'Scores for all time', self.show_alltime_scores),
            (['yesterday'], 'Scores for yesterday', self.show_yesterday_scores),
            (['today'], 'Scores for today', self.show_today_scores),
            (['help'], 'Show this help info', self.help),
        )

    @staticmethod
    def _answer_variants(answer):
        filters = [
            lambda x: [unidecode.unidecode(x)] if unidecode.unidecode(x) != x else [],
            lambda x: [re.sub(r'[0-9]+(?:[\.,][0-9]+)?', lambda y: num2words(y.group(0)), x)],
            lambda x: [x.replace(a, b) for a,b in [['&', 'and'],['%', 'percent']] if a in x],
            lambda x: [x[len(a):] for a in ['a ', 'an ', 'the '] if x.startswith(a)],
            lambda x: [''.join([a for a in x if a not in ' '])],
            lambda x: [''.join([a for a in x if a not in '\'().,"-'])],
        ]

        possible_answers = [answer.lower()]
        for filter in filters:
            for possible_answer in possible_answers:
                try:
                    possible_answers = list(set([*possible_answers, *filter(possible_answer)]))
                except Exception as ex:
                    logging.exception(ex)

        return possible_answers

    @staticmethod
    def _do_check_answer(answer, correct_answer, match_character_count):
        correct_answer_variations = TriviaCore._answer_variants(correct_answer)
        given_answer_variations = TriviaCore._answer_variants(answer)

        logging.debug(
            'Correct answers:\n'
            + str(correct_answer_variations)
            + '\nGiven answers:\n'
            + str(given_answer_variations)
        )

        for correct_answer_variation in correct_answer_variations:
            for given_answer_variation in given_answer_variations:

                if (len(given_answer_variation.strip(' ')) >= min(match_character_count, len(correct_answer_variation)) and
                    given_answer_variation.strip() in correct_answer_variation):
                    return True

        return False

    def _add_user(self, uid):
        self._db.execute('add_player', {
            'uid': uid,
            'platform': self._platform
        }, auto_commit=True)

    def _user_wrong_answer(self, uid):
        self._db.execute('answer_wrong', {
            'uid': uid,
            'platform': self._platform,
        }, auto_commit=True)

    def _user_right_answer(self, uid, value):
        self._db.execute('answer_right', {
            'uid': uid,
            'platform': self._platform,
            'value': value,
        }, auto_commit=True)

    def _create_question_attempt(self):
        self.current_question = self._get_new_question()
        logging.info('New question id: ' + str(self.current_question['id']))
        self._db.execute(
            'create_question_attempt',
            (self.current_question['id'], int(time())),
            auto_commit=True
        )
        return self.current_question

    def get_player_stats_timeframe(self, uid, start_time, end_time=None):
        rows = self._db.select_iter('get_timeframe_scores', {
            'uid': uid,
            'start_time': start_time,
            'end_time': end_time,
        }, as_map=True)
        
        for row in rows:
            yield row

    def get_scores(self):
        rows = self._db.select_iter('get_scores', (self._platform,), as_map=True)
        scores = []
        for row in rows:
            scores.append(row)
        return scores

    def _update_question_attempt(self, attempts, players, correct_uid = None):
        logging.info('Question winner player id: ' + (str(correct_uid) or 'none'))
        params = {
            'attempts': attempts,
            'players': players,
            'player_id': None,
            'complete_time': int(time()),
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

    def exit(self, *_, **kwargs):
        self._post_message_handler('exit')
        #if kwargs.get('user') == self._config['admin']:
        #    self.post_message(text='ok bye', channel=kwargs['channel'])
        #    self.do_exit()

    def help(self, *_, **kwargs):
        self._post_message_handler('help')
        #template = '!{:<20}{}'
        #commands = '\n'.join([template.format(x[0][0], x[1]) for x in self.commands() if x[1] is not None])
        #self.post_message('```{}```'.format(commands), channel=kwargs.get('channel'))

    def uptime(self, *_, **kwargs):
        self._post_message_handler('uptime')
        #uptime = int(time.time()) - int(self._starttime)
        #uptime_str = "{:0>8}".format(str(datetime.timedelta(seconds=uptime)))
        #self.post_message(uptime_str, channel=kwargs['channel'])

    def show_today_scores(self, *_, **kwargs):
        self._post_message_handler('today')
        #today_start = self.timestamp_midnight()
        #self.show_scores(today_start, None, channel=kwargs.get('channel'))

    def show_yesterday_scores(self, *_, suppress_no_scores=False, **kwargs):
        self._post_message_handler('yesterday')
        #yesterday_start = self.timestamp_midnight(1)
        #yesterday_end = self.timestamp_midnight()
        #self.show_scores(yesterday_start, yesterday_end, suppress_no_scores=suppress_no_scores, channel=kwargs.get('channel'))

    def show_alltime_scores(self, *_, **kwargs):
        self._post_message_handler('alltime')
        #start = 0
        #self.show_scores(start, None, 'Alltime Scores', channel=kwargs.get('channel'))

    def show_scores(self, start, end, title=None, suppress_no_scores=False, channel=None):
        return
        #if title is None:
        #    title = 'Scoreboard for {}'.format(self.ftime(start))

        #scores = list(self._trivia.get_player_stats_timeframe(None, start, end))

        #if suppress_no_scores and len(scores) == 0:
        #    return

        #for score in scores:
        #    try:
        #        # Get the current display name from slack, limit to 32 chars
        #        score['name'] = self.get_username(score['uid'])[:32]
        #    except SlackApiError as ex:
        #        # This uid no longer exists on the slack team
        #        score['name'] = '(user gone)'

        #title2 = '=' * len(title)
        #scoreboard = self.format_scoreboard(scores)
        #self.post_message('```{}\n{}\n{}```'.format(title, title2,scoreboard), channel=channel)