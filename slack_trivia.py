import os
import json
import html
import signal
import logging
import datetime
import time
from slack_sdk.rtm_v2 import RTMClient
from slack_sdk.errors import SlackApiError
from trivia_database import TriviaDatabase
from threading import Lock
from apscheduler.schedulers.background import BackgroundScheduler
from tabulate import tabulate

NAME_CACHE_SECONDS = 12 * 60 * 60

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
        
        self._names_cache = {}

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
                time.sleep(1)

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
        name, name_time = self._names_cache.get(uid, ('???', 0))

        if time.time() > name_time + NAME_CACHE_SECONDS:
            name_priority = [
                'display_name_normalized',
                'real_name_normalized',
            ]
            logging.info('Getting username for uid: ' + uid)
            user = self._client.web_client.users_info(user=uid)['user']['profile']
            for name_type in name_priority:
                if name_type in user and user[name_type] is not None and user[name_type] != '':
                    name = user[name_type]
                    self._names_cache[uid] = (name, time.time())
                    break

        return name

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