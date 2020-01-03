__author__ = 'Zachery Thomas'

import re
import random
import os
import json
import bson

import config
from pymongo import MongoClient
from teams_api import TeamsApi

BEARER = os.getenv('BEARER')
API = TeamsApi(BEARER)

MONGO_USERNAME = os.getenv('MONGO_INITDB_ROOT_USERNAME')
MONGO_PASSWORD = os.getenv('MONGO_INITDB_ROOT_PASSWORD')


client = MongoClient('mongo', username=MONGO_USERNAME, password=MONGO_PASSWORD, port=27017)
trivia_db = client.trivia

questions_collection = trivia_db.questions
rooms_collection = trivia_db.rooms

def format_text(text):
    """Formats text for processing"""
    text = text.lower()
    text = text.replace('jeopardy!', '')
    text = text.replace('what is', '')
    text = text.replace('what are', '')

    text = text.strip()
    return text


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

    if answer.endswith('s'):
        possible_answers.append(answer[:-1])

    if answer.endswith('ing'):
        possible_answers.append(answer[:-3])

    # try adding an s at the end
    possible_answers.append(answer + 's')

    # try adding an ed at the end
    possible_answers.append(answer + 'ed')

    # try adding an ed at the end
    possible_answers.append(answer + 'ing')

    return possible_answers


def random_question():
    formatted_regex = [ bson.Regex.from_native(re.compile(cat)) for cat in config.ACCEPTED_CATEGORIES ]
    for index in range(len(formatted_regex)):
        formatted_regex[index].flags ^= re.UNICODE

    question_list = [doc for doc in questions_collection.find({
                        'value': { '$lte': config.MAX_QUESTION_VAL },
                        'category': { '$in': formatted_regex },
                        'air_date': { '$gt': '2010-01-01' }
                    })]

    while True:
        question = random.choice(question_list)

        # only word characters in answer
        if re.search(r'[^a-zA-Z0-9_ ]', question['answer']):
            continue

        # no html in questions
        if '<' in question['question'] or '>' in question['question']:
            continue

        question['question'] = question['question'][1:-1]
        return question


def new_game(room_id):
    question = random_question()
    entry = {
        'roomId': room_id,
        'roomName': API.get_room_name(room_id),
        'users': {},
        'currentQuestion': question
    }

    rooms_collection.insert_one(entry)

    text = f'Welcome to Jeopardy!  \n' \
           f"The category is {question['category']} for ${question['value']}\n\n" \
           f"{question['question']}"

    API.send_message(text, room_id)


def special_commands(room_id, text, room_entry):
    if text == '.debug':
        API.send_message(str(room_entry), room_id)
        return

    if text == '.question':
        API.send_message(str(room_entry['currentQuestion']['question']), room_id)
        return

    if text == '.leaderboard':
        leaderboard = [room_entry['users'][entry] for entry in room_entry['users']]

        leaderboard = sorted(leaderboard, key=lambda user: user['score'], reverse=True)

        text = f'```\n{"Name:": <20}Score:\n'
        for user in leaderboard:
            text += f'{user["name"]: <20}{user["score"]}\n'
        text += '```'

        API.send_message(text, room_id)
        return

    if text == '.skip':
        question = random_question()

        text = f"The correct answer for {room_entry['currentQuestion']['question']} is: `{room_entry['currentQuestion']['answer']}`\n\n" \
            f"The new category is `{question['category']}` for `${question['value']}`:  \n" \
            f"**{question['question']}**"

        query = {
            "roomId": room_id
        }

        newvalues = {
            '$set': {
                'currentQuestion': question
            }
        }

        print(json.dumps(newvalues, indent=4))

        rooms_collection.update(query, newvalues)

        API.send_message(text, room_id)
        return


    text = '.help, shows this screen  \n' \
        '.question, repeats the question  \n' \
        '.leaderboard, displays the leaderboard  \n' \
        '.skip, skips the question. no points recorded  \n'

    API.send_message(text, room_id)


def right_answer(room_id, person_id, person_name, room_entry):
    question = random_question()

    text = f"{random.choice(config.RIGHT_TEXT)}\n\n" \
        f"${room_entry['currentQuestion']['value']} for {person_name}!\n\n" \
        f"The category is `{question['category']}` for `${question['value']}`:  \n" \
        f"**{question['question']}**"

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

    print(json.dumps(newvalues, indent=4))

    rooms_collection.update(query, newvalues)

    API.send_message(text, room_id)

def wrong_answer(room_id, person_id, person_name, room_entry):
    text = f"{random.choice(config.WRONG_ANSWER)}\n\n" \
        f"Subtract ${room_entry['currentQuestion']['value']} from {person_name}"

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


def tick(room_id, person_id, message_id):
    room_entry = rooms_collection.find_one({'roomId': room_id})

    # if no room entry in db, start a new game
    if not room_entry:
        new_game(room_id)

    # else it's an ongoing game
    else:
        text = API.get_message(message_id).lower()
        text = format_text(text)

        answer = room_entry['currentQuestion']['answer'].lower()
        possible_answers = get_possible_answers(answer)
        print('entered text:', text)
        print('answer:', possible_answers)

        if text.startswith('.'):
            special_commands(room_id, text, room_entry)

        elif text in possible_answers:
            person_name = API.get_person_name(person_id)
            right_answer(room_id, person_id, person_name, room_entry)

        else:
            person_name = API.get_person_name(person_id)
            wrong_answer(room_id, person_id, person_name, room_entry)