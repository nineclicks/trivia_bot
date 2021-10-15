from trivia_core import TriviaCore

trivia = TriviaCore('abc', 'trivia_test.db', 'test', {'character_count': 5})

@trivia.post_question
def show_question(**question):
    print(question)

@trivia.post_message
def show_message(message):
    print(message)

def correct(test = None):
    print('correct: ', test)


while True:
    answer = input(': ')
    if answer == '':
        break

    uid, answer = answer.split(',')
    if answer.startswith('!'):
        callback = lambda x: print(x)
        trivia.handle_command(uid, answer[1:], callback)
    else:
        callback = lambda: correct(uid + ', ' + answer)
        trivia.attempt_answer(uid, answer, callback)