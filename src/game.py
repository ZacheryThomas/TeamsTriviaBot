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

clues_collection = trivia_db.clues
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

    possible_answers.append(answer.replace(' ', ''))

    if '"' in answer:
        possible_answers.append(answer.replace('"', ''))

    if '\'' in answer:
        possible_answers.append(answer.replace('\'', ''))

    if answer.endswith('s'):
        possible_answers.append(answer[:-1] + 'ies')

    if answer.endswith('s'):
        possible_answers.append(answer[:-1])

    if answer.endswith('es'):
        possible_answers.append(answer[:-2])

    if answer.endswith('ing'):
        possible_answers.append(answer[:-3])

    # try adding an s at the end
    possible_answers.append(answer + 's')

    # try adding an ed at the end
    possible_answers.append(answer + 'ed')

    # try adding an ed at the end
    possible_answers.append(answer + 'ing')

    if answer.startswith('a '):
        possible_answers += [ans[2:] for ans in possible_answers]

    elif answer.startswith('an '):
        possible_answers += [ans[3:] for ans in possible_answers]

    elif answer.startswith('the '):
        possible_answers += [ans[4:] for ans in possible_answers]

    permute = []
    for ans in possible_answers:
        permute += ['a ' + ans, 'an ' + ans, 'the ' + ans]

    possible_answers += permute
    return possible_answers


def random_clue(prev_clues):
    formatted_regex = [ bson.Regex.from_native(re.compile(cat)) for cat in config.ACCEPTED_CATEGORIES ]
    for index in range(len(formatted_regex)):
        formatted_regex[index].flags ^= re.UNICODE

    while True:
        clue = list(clues_collection.aggregate([
                                                {
                                                    '$match': {
                                                        'value': { '$lte': config.MAX_CLUE_VAL },
                                                        'category': { '$in': formatted_regex },
                                                        'air_date': { '$gt': config.MIN_DATE }
                                                    },
                                                },
                                                {
                                                    '$sample': { 'size': 1 }
                                                }
                                            ]))[0]

        print('possible clue:', clue['clue'])

        if prev_clues is None:
            return clue

        if clue['_id'] in prev_clues:
            continue

        # only word characters and spaces in answer
        if re.search(r'[^a-zA-Z0-9_ ]', clue['answer']):
            continue

        # no html in clues
        if '<' in clue['clue'] or '>' in clue['clue']:
            continue

        print('selected clue:', clue['clue'])
        return clue


def pp_clue(clue):
    comments = ""
    if 'comments' in clue:
        if clue['comments']:
            comments = f"With this clue: {clue['comments'].split(':')[1][:-1]}  \n"

    return f"The category is `{clue['category']}` for `${clue['value']}`:  \n" \
           f"{comments}" \
           f"**{clue['clue']}**"


def special_commands(room_id, room_type, person_id, text, room_entry):
    if text == '.clue':
        API.send_message(pp_clue(room_entry['currentClue']), room_id)
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
        if not 'skipAttempt' in room_entry and room_type == 'group':
            newvalues = {
                '$set': {
                    'skipAttempt': person_id,
                }
            }

            query = {
                "roomId": room_id,
            }

            rooms_collection.update(query, newvalues)

            API.send_message('Skip attempt started. Need another vote to proceed!', room_id)
            return

        if 'skipAttempt' in room_entry and room_type == 'group':
            if room_entry['skipAttempt'] == person_id:
                API.send_message('Another person besides you must vote to skip.', room_id)
                return

        prev_clues = room_entry['previousClues'] + [room_entry['currentClue']['_id']] if 'previousClues' in room_entry else [room_entry['currentClue']['_id']]
        if len(prev_clues) > config.PREV_CLUE_CACHE:
            prev_clues = prev_clues[-config.PREV_CLUE_CACHE:]

        clue = random_clue(prev_clues)

        text = f"The correct answer for **{room_entry['currentClue']['clue']}** is: `{room_entry['currentClue']['answer']}`\n\n" \
               + pp_clue(clue)

        query = {
            "roomId": room_id
        }

        newvalues = {
            '$set': {
                'currentClue': clue,
            },
            '$unset': {
                'skipAttempt': person_id,
            }
        }

        print(newvalues)

        rooms_collection.update(query, newvalues)

        API.send_message(text, room_id)
        return


    text = '`.help` shows this output  \n' \
           '`.clue` repeats the clue  \n' \
           '`.leaderboard` displays the leaderboard  \n' \
           '`.skip` skips the clue. no points recorded  \n'

    API.send_message(text, room_id)


def new_game(room_id):
    clue = random_clue(None)
    entry = {
        'roomId': room_id,
        'roomName': API.get_room_name(room_id),
        'users': {},
        'currentClue': clue
    }

    rooms_collection.insert_one(entry)

    text = f'Welcome to Jeopardy!  \n' \
           + pp_clue(clue)

    API.send_message(text, room_id)


def right_answer(room_id, person_id, person_name, room_entry):
    prev_clues = []
    if 'previousClues' in room_entry:
        prev_clues = room_entry['previousClues'] + [room_entry['currentClue']['_id']]
    else:
        prev_clues = [room_entry['currentClue']['_id']]

    if len(prev_clues) > config.PREV_CLUE_CACHE:
        prev_clues = prev_clues[-config.PREV_CLUE_CACHE:]

    clue = random_clue(prev_clues)

    query = {
        "roomId": room_id
    }

    try:
        score = room_entry['users'][person_id]['score']
    except KeyError:
        score = 0
    score += room_entry['currentClue']['value']

    text = f"{random.choice(config.RIGHT_TEXT)}  \n" \
           f"`${room_entry['currentClue']['value']}` for {person_name.firstName}!\n\n" \
           + pp_clue(clue)

    newvalues = {
        '$set': {
            'currentClue': clue,
            'previousClues': prev_clues,
            f'users.{person_id}': {
                'score': score,
                'name': f'{person_name.firstName} {person_name.lastName[0]}'
            }
        },
        '$unset': {
            'skipAttempt': person_id,
        }
    }

    print(newvalues)

    rooms_collection.update(query, newvalues)

    API.send_message(text, room_id)


def wrong_answer(room_id, person_id, person_name, room_entry, closeness):
    text = f"{random.choice(config.WRONG_TEXT) if closeness < 80 else random.choice(config.CLOSE_TEXT)}\n\n" \
        f"Subtract `${room_entry['currentClue']['value']}` from {person_name.firstName}"

    try:
        score = room_entry['users'][person_id]['score']
    except KeyError:
        score = 0

    score -= room_entry['currentClue']['value']

    query = {
        "roomId": room_id
    }

    newvalues = {
        '$set': {
            f'users.{person_id}': {
                'score': score,
                'name': f'{person_name.firstName} {person_name.lastName[0]}'
            }
        }
    }

    rooms_collection.update(query, newvalues)

    API.send_message(text, room_id)


def tick(room_id, room_type, person_id, message_id):
    room_entry = rooms_collection.find_one({'roomId': room_id})

    # if no room entry in db, start a new game
    if not room_entry:
        new_game(room_id)

    # else it's an ongoing game
    else:
        text = API.get_message(message_id).lower()
        text = format_text(text)

        answer = room_entry['currentClue']['answer'].lower()
        possible_answers = get_possible_answers(answer)
        print('entered text:', text)
        print('answer:', possible_answers)

        if text.startswith('.'):
            special_commands(room_id, room_type, person_id, text, room_entry)

        elif text in possible_answers:
            person_name = API.get_person_name(person_id)
            right_answer(room_id, person_id, person_name, room_entry)

        else:
            import difflib

            seq = difflib.SequenceMatcher(None, text, answer)
            closeness = seq.ratio()*100

            person_name = API.get_person_name(person_id)
            wrong_answer(room_id, person_id, person_name, room_entry, closeness)