import os
import json
import html
import signal
import logging
import datetime
import time
from time import sleep
from slack_sdk.rtm_v2 import RTMClient
from slack_sdk.errors import SlackApiError
from trivia_database import TriviaDatabase
from threading import Lock
from apscheduler.schedulers.background import BackgroundScheduler
from tabulate import tabulate


class SlackTrivia:

    @staticmethod
    def timestamp_midnight(days_ago=0):
        return int(datetime.datetime.combine(datetime.datetime.today() - datetime.timedelta(days=days_ago), datetime.time.min).timestamp())

    @staticmethod
    def ftime(timestamp):
        return time.strftime('%A %B %d %Y',time.localtime(int(timestamp)))

    def __init__(self, config_filename):
        logging.info('Starting SlackTrivia')
        self._lock = Lock()
        self._attempts = []
        self._load_config(config_filename)
        self._client = RTMClient(token=self._config['slack_bot_token'])
        self._setup_handle_message()
        self._setup_hello()
        self._starttime = time.time()
        self._trivia = TriviaDatabase(
            self._config['database'],
            self._team_id(),
            self._config['matching']
        )

        self._sched = BackgroundScheduler()
        self._sched.start()  

        self._job = self._sched.add_job(
            self.show_yesterday_scores,
            'cron',
            **self._config['scoreboard_time'],
            kwargs={'suppress_no_scores': True},
            replace_existing=True)

        self._max_tries = self._config.get('max_tries', 2)

        self._client.start()

    def _load_config(self, filename):
        with open(filename, 'r') as fp:
            self._config = json.load(fp)

    def _team_id(self):
        return self._client.web_client.team_info()['team']['id']

    def post_message(self, text, **kwargs):
        # Delete any None value args so they don't overwrite on "update()"
        kwargs = {k:v for k,v in kwargs.items() if v is not None}

        message_args = {
            'channel': self._config['trivia_channel'],
            'text': text,
            **self._config['bot']
        }
        message_args.update(kwargs)
        tries = 0
        while tries < max(self._max_tries, 1):
            tries += 1
            try:
                return self._client.web_client.chat_postMessage(**message_args)
            except Exception as ex:
                logging.exception(ex)
                logging.error('Slack send error. Try # ' + str(tries))
                sleep(1)

    @staticmethod
    def do_exit():
        os.kill(os.getpid(), signal.SIGTERM)

    def _setup_hello(self):
        @self._client.on('hello')
        def hello(client: RTMClient, event: dict):
            if self._trivia.current_question is None:
                self.new_question()

    def _setup_handle_message(self):
        @self._client.on('message')
        def handle_message(client: RTMClient, event: dict):
            print(event)
            try:
                with self._lock:
                    if (
                        event['type'] != 'message'
                        or 'subtype' in event
                        or 'thread_ts' in event
                        or (event['channel'] != self._config['trivia_channel'] and event['user'] != self._config['admin'])
                        ):
                        return

                    user: str = event['user']
                    text: str = html.unescape(event['text'])
                    channel: str = event['channel']
                    ts = event['ts']

                    if text.strip().startswith('!'):
                        self.handle_command(user, text.strip().lower()[1:], ts, channel)
                    else:
                        self.handle_answer(user, text, ts)
            except Exception as ex:
                logging.exception(ex)

    def get_username(self, uid):
        name_priority = [
            'display_name_normalized',
            'real_name_normalized',
        ]
        user = self._client.web_client.users_info(user=uid)['user']['profile']
        for name_type in name_priority:
            if name_type in user and user[name_type] is not None and user[name_type] != '':
                return user[name_type]
        return '???'

    def new_question(self, message = None):
        self._attempts = []
        question = self._trivia.make_question_attempt()
        question['comment'] = '_{}_'.format(question['comment']) if question['comment'] else ''

        q_template = '({year}) *{category}* {comment} for *{value}*\n>{question}'
        if message:
            q_template = message + '\n' + q_template

        self.post_message(q_template.format(**question))

    def commands(self):
        return (
            (['exit'], None, self.exit),
            (['uptime'], None, self.uptime),
            (['new', 'trivia new'], 'Skip to the next question', lambda *_, **__: self.update_attempt(None, None)),
            (['alltime', 'score', 'scores'], 'Scores for all time', self.show_alltime_scores),
            (['yesterday'], 'Scores for yesterday', self.show_yesterday_scores),
            (['today'], 'Scores for today', self.show_today_scores),
            (['help'], 'Show this help info', self.help),
        )

    def exit(self, *_, **kwargs):
        if kwargs.get('user') == self._config['admin']:
            self.post_message(text='ok bye', channel=kwargs['channel'])
            self.do_exit()

    def help(self, *_, **kwargs):
        template = '!{:<20}{}'
        commands = '\n'.join([template.format(x[0][0], x[1]) for x in self.commands() if x[1] is not None])
        self.post_message('```{}```'.format(commands), channel=kwargs.get('channel'))

    def handle_command(self, user, text, ts, channel):
        for command in self.commands():
            if text in command[0]:
                command[2](user=user, text=text, ts=ts, channel=channel)
                break

    @staticmethod
    def format_scoreboard(scores):
        cols = [
            ('rank', lambda x: x),
            ('name', lambda x: x),
            ('score', lambda x: '{:,}'.format(x)),
            ('correct', lambda x: x),
        ]

        return tabulate([{col: fn(x[col]) for col, fn in cols} for x in scores], headers='keys')

    def uptime(self, *_, **kwargs):
        uptime = int(time.time()) - int(self._starttime)
        uptime_str = "{:0>8}".format(str(datetime.timedelta(seconds=uptime)))
        self.post_message(uptime_str, channel=kwargs['channel'])

    def show_today_scores(self, *_, **kwargs):
        today_start = self.timestamp_midnight()
        self.show_scores(today_start, None, channel=kwargs.get('channel'))

    def show_yesterday_scores(self, *_, suppress_no_scores=False, **kwargs):
        yesterday_start = self.timestamp_midnight(1)
        yesterday_end = self.timestamp_midnight()
        self.show_scores(yesterday_start, yesterday_end, suppress_no_scores=suppress_no_scores, channel=kwargs.get('channel'))

    def show_alltime_scores(self, *_, **kwargs):
        start = 0
        self.show_scores(start, None, 'Alltime Scores', channel=kwargs.get('channel'))

    def show_scores(self, start, end, title=None, suppress_no_scores=False, channel=None):
        if title is None:
            title = 'Scoreboard for {}'.format(self.ftime(start))

        scores = list(self._trivia.get_player_stats_timeframe(None, start, end))

        if suppress_no_scores and len(scores) == 0:
            return

        for score in scores:
            try:
                # Get the current display name from slack, limit to 32 chars
                score['name'] = self.get_username(score['uid'])[:32]
            except SlackApiError as ex:
                # This uid no longer exists on the slack team
                score['name'] = '(user gone)'

        title2 = '=' * len(title)
        scoreboard = self.format_scoreboard(scores)
        self.post_message('```{}\n{}\n{}```'.format(title, title2,scoreboard), channel=channel)


    def update_attempt(self, winning_user, ts):
        attempt_users = set(self._attempts)
        for attempt_user in attempt_users:
            self._trivia.add_user(attempt_user)
            if winning_user != attempt_user:
                self._trivia.user_wrong_answer(attempt_user)
            else:
                self._trivia.user_right_answer(attempt_user, self._trivia.current_question['value'])

        self._trivia.update_question_attempt(
            attempts=len(self._attempts),
            players=len(attempt_users),
            correct_uid=winning_user,
        )

        message = '{}: *{}*'.format('Correct' if winning_user is not None else 'Answer', self._trivia.current_question['answer'])
        if winning_user is not None:
            try:
                self._client.web_client.reactions_add(
                    channel = self._config['trivia_channel'],
                    name = 'white_check_mark',
                    timestamp = ts,
                )
            except Exception as ex:
                logging.exception(ex)
            status = next(self._trivia.get_player_stats_timeframe(winning_user, self.timestamp_midnight()), None) # TODO deal with None case
            score = status['score']
            rank = status['rank']
            message += ' -- {} (today: {:,} #{})'.format(self.get_username(winning_user), score, rank)
        self.new_question(message)

    def handle_answer(self, user, text, ts):
        # need to make this more generic to handle skip and no right answer/user
        self._attempts.append(user)
        if self._trivia.check_answer(text):
            self.update_attempt(user, ts)
