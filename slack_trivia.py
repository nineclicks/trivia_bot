import os
import json
import html
import signal
import logging
from slack_sdk.rtm_v2 import RTMClient
from slack_sdk.errors import SlackApiError
from trivia_database import TriviaDatabase
from threading import Lock
from datetime import datetime, time, timedelta
from time import localtime, strftime
from apscheduler.schedulers.background import BackgroundScheduler


class SlackTrivia:

    @staticmethod
    def timestamp_midnight(days_ago=0):
        return int(datetime.combine(datetime.today() - timedelta(days=days_ago), time.min).timestamp())

    @staticmethod
    def ftime(timestamp):
        return strftime('%A %B %d %Y',localtime(int(timestamp)))

    def __init__(self, config_filename):
        logging.info('Starting SlackTrivia')
        self._lock = Lock()
        self._attempts = []
        self._load_config(config_filename)
        self._client = RTMClient(token=self._config['slack_bot_token'])
        self._setup_handle_message()
        self._setup_hello()
        self._trivia = TriviaDatabase(
            self._config['database'],
            self._team_id(),
            self._config['matching']
        )

        self._sched = BackgroundScheduler()
        self._sched.start()  

        self._job = self._sched.add_job(self.show_yesterday_scores, 'cron', **self._config['scoreboard_time'], replace_existing=True)

        self._client.start()

    def _load_config(self, filename):
        with open(filename, 'r') as fp:
            self._config = json.load(fp)

    def _team_id(self):
        return self._client.web_client.team_info()['team']['id']

    def post_message(self, text, **kwargs):
        message_args = {
            'channel': self._config['trivia_channel'],
            'text': text,
            **self._config['bot']
        }
        message_args.update(kwargs)
        return self._client.web_client.chat_postMessage(**message_args)

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
                        or event['channel'] != self._config['trivia_channel']
                        ):
                        return

                    user: str = event['user']
                    text: str = html.unescape(event['text'])
                    ts = event['ts']

                    if text.strip().startswith('!'):
                        self.handle_command(user, text.strip().lower()[1:], ts)
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


    def handle_command(self, user, text, ts):
        if text == 'exit' and user == self._config['admin']:
            ts = self.post_message(text='ok bye')['ts']
            self.do_exit()
        elif text in ['trivia new', 'new']:
            self.update_attempt(None, None)
        elif text in ['score', 'scores', 'leaderboard']:
            self.show_scores()
        elif text in ['yesterday']:
            self.show_yesterday_scores()

    def show_scores(self):
        header = {'rank': 'Rank', 'name': 'Name', 'score': 'Score', 'correct': 'Right', 'incorrect': 'Wrong', 'pct': ''}
        line_template = '{rank:<5} {name:<30} {score:<13,} {correct:<6} {incorrect:<6} {pct:.1f}%'

        # remove comma from template since we can't comma separate the word "Score"
        lines = [line_template.replace(',','').replace(':.1f','').format(**header)]
        scores = self._trivia.get_scores()
        for i, score in enumerate(scores):
            score['pct'] = score['correct'] / (score['correct'] + score['incorrect']) * 100
            try:
                # Get the current display name from slack, limit to 20 chars
                score['name'] = self.get_username(score['uid'])[:28]
            except SlackApiError as ex:
                # This uid no longer exists on the slack team
                score['name'] = '(user gone)'

            lines.append(line_template.format(rank=i+1, **score))

        self.post_message('```{}```'.format('\n'.join(lines)))

    def show_yesterday_scores(self):
        header = {'rank': 'Rank', 'name': 'Name', 'score': 'Score', 'correct': 'Correct Answers'}
        line_template = '{rank:<5} {name:<30} {score:<13,} {correct:<16}'

        # remove comma from template since we can't comma separate the word "Score"
        lines = [line_template.replace(',','').format(**header)]
        #scores = self._trivia.get_scores()
        yesterday_start = self.timestamp_midnight(1)
        yesterday_end = self.timestamp_midnight()
        scores = self._trivia.get_player_stats_timeframe(None, yesterday_start, yesterday_end)
        for score in scores:
            try:
                # Get the current display name from slack, limit to 20 chars
                score['name'] = self.get_username(score['uid'])[:28]
            except SlackApiError as ex:
                # This uid no longer exists on the slack team
                score['name'] = '(user gone)'

            lines.append(line_template.format(**score))

        if len(lines) == 1:
            return
        title = 'Scoreboard for {}'.format(self.ftime(yesterday_start))
        title2 = '=' * len(title)
        self.post_message('```{}\n{}\n{}```'.format(title, title2,'\n'.join(lines)))


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
