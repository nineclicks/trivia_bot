import sys
import logging
from slack_trivia import SlackTrivia

log_level = (sys.argv[1:2] or ['ERROR'])[0].upper()
logging.basicConfig(level = log_level)

trivia = SlackTrivia('config.json')