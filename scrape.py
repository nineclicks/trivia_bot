import re
import requests
import html
import sqlite3
from time import sleep
REG_CATEGORIES = r'"category_name">(.*?)<\/td>[\s\S]*?"category_comments">(.*?)<\/td>'
REG_QUESTIONS = r'(?:correct_response&quot;&gt;(.*?)&lt;\/em&gt;[\s\S]*?class="clue_text">(.*?)<\/td>|<td class="clue">\s*?<\/td>)'
REG_EPS = r'\"(https:\/\/www\.j-archive\.com\/showgame\.php\?game_id=\d+)\"'
REG_CAT_COMMENT = r'\(.+?:\s+(.*)\)'
REG_HTML_TAGS = r'<[^>]+>'
REG_SHOW_NUM = r'<div id=\"game_title\"><h1>Show #(\d+).*?(\d{4})<\/h1>'

DB_PATH = 'j_questions.db'

sample_page = 'https://www.j-archive.com/showgame.php?game_id=7094'

def build_tables():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS category
               (id INTEGER NOT NULL PRIMARY KEY, show_number number, show_year number, title text, comment text)''')

    cur.execute('''CREATE TABLE IF NOT EXISTS question
               (id INTEGER NOT NULL PRIMARY KEY, category_id number, value number, question text, answer text, non_text number)''')

    con.commit()
    con.close()

def parse_page(url):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cats = []
    questions = []
    scores = [200, 400, 600, 800, 1000]
    page_content = requests.get(url).content.decode('utf-8')
    show_info = re.search(REG_SHOW_NUM, page_content)
    show_num = int(show_info[1])
    show_year = int(show_info[2])
    
    cur.execute('''SELECT DISTINCT show_number FROM category WHERE show_number = ?''', (show_num, ))
    if len(cur.fetchall()) > 0:
        return

    matches = re.findall(REG_CATEGORIES, page_content)[:-1]
    if len(matches) != 12:
        con.rollback()
        raise IndexError('Wrong number of categories found! ' + str(len(matches)))

    for match in matches:
        category = html.unescape(match[0])
        comment = html.unescape(match[1])
        com_match = re.match(REG_CAT_COMMENT, comment)
        if com_match:
            comment = com_match[1]

        if comment == '':
            comment = None

        cur.execute('''INSERT INTO category (show_number, show_year, title, comment) VALUES (?, ?, ?, ?)''', (show_num, show_year, category, comment))
        cats.append(cur.lastrowid)

    matches = re.findall(REG_QUESTIONS, page_content)
    if len(matches) != 60:
        con.rollback()
        raise IndexError('Wrong number of questions found!' + str(len(matches)))

    for i, match in enumerate(matches):
        if len(match) < 2 or match[0] == '' or match[1] == '':
            continue

        cat = cats[(i % 6) + 6 * (i // 30)]
        score = scores[(i % 30) // 6]
        question = match[1]
        non_text = 0
        if 'a href' in question.lower():
            non_text = 1
        question = re.sub(REG_HTML_TAGS, '', html.unescape(question)).replace('\\', '')
        answer = re.sub(REG_HTML_TAGS, '', html.unescape(match[0])).replace('\\', '')
        cur.execute('''INSERT INTO question (category_id, value, question, answer, non_text) VALUES (?, ?, ?, ?, ?)''', 
        (cat, score, question, answer, non_text))

    con.commit()
    con.close()

def scan_season(url):
    page_content = requests.get(url).content.decode('utf-8')
    matches = re.finditer(REG_EPS, page_content)

    for match in matches:
        ep_url = match[1]
        print(ep_url)
        parse_page(ep_url)
        sleep(4)


build_tables()
#parse_page('https://www.j-archive.com/showgame.php?game_id=7066')
scan_season('https://www.j-archive.com/showseason.php?season=37')