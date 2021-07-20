import re
import requests
import html
import sqlite3
REG_CATEGORIES = r'"category_name">(.*?)<\/td>[\s\S]*?"category_comments">(.*?)<\/td>'
REG_QUESTIONS = r'correct_response&quot;&gt;(.*?)&lt;\/em&gt;[\s\S]*?class="clue_text">(.*?)<\/td>'
REG_EPS = r'\"(https:\/\/www\.j-archive\.com\/showgame\.php\?game_id=\d+)\"'
REG_CAT_COMMENT = r'\(.+?:\s+(.*)\)'
REG_HTML_TAGS = r'<[^>]+>'
REG_SHOW_NUM = r'<div id=\"game_title\"><h1>Show #(\d+)'

sample_page = 'https://www.j-archive.com/showgame.php?game_id=7094'

def build_tables():
    con = sqlite3.connect('example.db')
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS category
               (id INTEGER NOT NULL PRIMARY KEY, show_number number, title text, comment text)''')

    cur.execute('''CREATE TABLE IF NOT EXISTS question
               (id INTEGER NOT NULL PRIMARY KEY, category_id number, value number, question text, answer text)''')

    con.commit()
    con.close()

def parse_page(url):
    con = sqlite3.connect('example.db')
    cur = con.cursor()
    cats = []
    questions = []
    scores = [200, 400, 600, 800, 1000]
    page_content = requests.get(url).content.decode('utf-8')
    show_num = int(re.search(REG_SHOW_NUM, page_content)[1])
    
    cur.execute('''SELECT DISTINCT show_number FROM category WHERE show_number = ?''', (show_num, ))
    if len(cur.fetchall()) > 0:
        return

    matches = re.findall(REG_CATEGORIES, page_content)[:-1]
    if len(matches) != 12:
        raise IndexError('Wrong number of categories found!')

    for match in matches:
        category = html.unescape(match[0])
        comment = html.unescape(match[1])
        com_match = re.match(REG_CAT_COMMENT, comment)
        if com_match:
            comment = com_match[1]

        if comment == '':
            comment = None

        cur.execute('''INSERT INTO category (show_number, title, comment) VALUES (?, ?, ?)''', (show_num, category, comment))
        cats.append(cur.lastrowid)
    print(cats)

    matches = re.findall(REG_QUESTIONS, page_content)
    if len(matches) != 60:
        raise IndexError('Wrong number of categories found!')

    for i, match in enumerate(matches):
        cat = cats[(i % 6) + 6 * (i // 30)]
        score = scores[(i % 30) // 6]
        question = re.sub(REG_HTML_TAGS, '', html.unescape(match[1]))
        answer = re.sub(REG_HTML_TAGS, '', html.unescape(match[0]))
        questions.append([question, answer])
        print(cat, score, question, '>', answer)
    con.commit()
    con.close()



build_tables()
parse_page(sample_page)