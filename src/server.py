__author__ = 'Zachery Thomas'

import re
import random
import os
import json
import time
import threading

from pymongo import MongoClient
from bottle import post, request, run
from teams_api import TeamsApi

BEARER = os.getenv('BEARER')
MYID = os.getenv('MYID')
API = TeamsApi(BEARER)

MONGO_USERNAME = os.getenv('MONGO_INITDB_ROOT_USERNAME')
MONGO_PASSWORD = os.getenv('MONGO_INITDB_ROOT_PASSWORD')

client = MongoClient('localhost', username=MONGO_USERNAME, password=MONGO_PASSWORD, port=27017)
trivia_db = client.trivia

questions_collection = trivia_db.questions
rooms_collection = trivia_db.rooms

MAX_QUESTION_VAL = 800
ACCEPTED_CATEGORIES = ['SCIENCE', 'SCIENCE TERMS', 'STUPID ANSWERS', 'FOOD & DRINK', 'WORLD HISTORY', 'BRAND NAMES']

MAX_MSG_LEN = 5000
TIMEOUT = 10 * 60 # ten min


def format_text(text):
    """Formats text for processing"""
    text = text.lower()
    text = text.replace('jeopardy!', '')
    text = text.replace('what is', '')
    text = text.replace('what are', '')

    text = text.strip()
    return text


class WortherThread(threading.Thread):
    def __init__(self, container):
        threading.Thread.__init__(self)
        self.container = container
        self.timeout = TIMEOUT
        self._running = True
        self.completed = True

    def run(self):
        while self._running and self.timeout > 0:
            print('Timeout in: ', self.timeout, ' seconds')
            self.timeout -= 1
            time.sleep(1)

        if self.timeout == 0:
            print("no answer")
            print("new question")

    def terminate(self):
        self._running = False


def get_possible_answers(answer):
    possible_answers = [answer]

    if '"' in answer:
        possible_answers.append(answer.replace('"', ''))

    if '\'' in answer:
        possible_answers.append(answer.replace('\'', ''))

    if answer.startswith('a '):
        possible_answers.append(answer[2:])

    if answer.startswith('an '):
        possible_answers.append(answer[3:])

    if answer.startswith('the '):
        possible_answers.append(answer[4:])

    if answer.endswith('s'):
        possible_answers.append(answer[:-1] + 'ies')
    return possible_answers


def randomQuestion():
    q = random.choice(
        [doc for doc in questions_collection.find({
            'value': { '$lte': MAX_QUESTION_VAL },
            'category': { '$in': ACCEPTED_CATEGORIES },
            'air_date': { '$gt': '2010-01-01' }
        })]
    )

    # no html in questions or answers
    if '<' in q['question'] or '>' in q['question'] or '<' in q['answer'] or '>' in q['answer']:
        return randomQuestion()

    else:
        return q


@post('/messages')
def messages():
    print('got post!')
    data = json.loads(request.body.read())['data']

    room_id = data['roomId']
    person_id = data['personId']
    message_id = data['id']

    print(person_id, MYID)
    if person_id == MYID:
        return

    room_entry = rooms_collection.find_one({'roomId': room_id})
    if not room_entry:
        question = randomQuestion()
        entry = {
            'roomId': room_id,
            'roomName': API.get_room_name(room_id),
            'users': {},
            'currentQuestion': question
        }
        print(entry)

        rooms_collection.insert_one(entry)

        text = f'''Welcome to Jeopardy!

The category is {question['category']}

{question['question']}'''

        API.send_message(text, room_id)

    else:
        text = API.get_message(message_id).lower()
        text = format_text(text)
        person_name = API.get_person_name(person_id)

        answer = room_entry['currentQuestion']['answer'].lower()
        possible_answers = get_possible_answers(answer)
        print('entered text:', text)
        print('answer:', possible_answers)

        if text == 'debug':
            API.send_message(str(room_entry), room_id)
            return

        if text == 'leaderboard':
            leaderboard = [room_entry['users'][entry] for entry in room_entry['users']]

            leaderboard = sorted(leaderboard, key=lambda user: user['score'])

            text = f'{"name:": <20}score:\n'
            for user in leaderboard:
                text += f'{user["name"]: <20}{user["score"]}\n'

            API.send_message(text, room_id)
            return


        if text in possible_answers:
            question = randomQuestion()

            right_text = [
                'Yes!',
                'That is correct.',
                'Right on!',
                'You did it. Im proud of you!',
                'That one was tough but you got it!',
                ':D',
                'Correct!',
                'Right!'
            ]

            text = f'''{random.choice(right_text)}

${room_entry['currentQuestion']['value']} for {person_name}!

The category is {question['category']}

{question['question']}
                '''

            query = {
                "roomId": room_id
            }

            try:
                score = room_entry['users'][person_id]['score']
            except KeyError:
                score = 0


            score += room_entry['currentQuestion']['value']

            newvalues = {
                '$set': {
                    'currentQuestion': question,
                    f'users.{person_id}': {
                        'score': score,
                        'name': person_name
                    }
                }
            }

            print(newvalues)

            rooms_collection.update(query, newvalues)

            API.send_message(text, room_id)

        else:
            wrong_text = [
                'Sorry dumdum, you\'re wrong!',
                'Nah, wrong answer, kid',
                'Ooops, thats not right!',
                'Lol, nah. That ain\'t it.',
                'Good try! But thats not right.',
                'No.',
                'Wrong!',
                'You fool! you utter nincompoop.',
                '...',
                'Wow. No.',
                'Cmon dawg. You know that ain\'t it.',
                'NooOOOOOooooo'
            ]

            text = f"""{random.choice(wrong_text)}

Subtract ${room_entry['currentQuestion']['value']} from {person_name}"""

            try:
                score = room_entry['users'][person_id]['score']
            except KeyError:
                score = 0

            score -= room_entry['currentQuestion']['value']

            query = {
                "roomId": room_id
            }

            newvalues = {
                '$set': {
                    f'users.{person_id}': {
                        'score': score,
                        'name': person_name
                    }
                }
            }

            rooms_collection.update(query, newvalues)

            API.send_message(text, room_id)


if __name__ == "__main__":
    run(host='0.0.0.0', port=80)
