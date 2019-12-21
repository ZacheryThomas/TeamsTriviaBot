import json

from pymongo import MongoClient

client = MongoClient()
trivia_db = client.trivia

questions_collection = trivia_db.questions
with open('./assets/questions.json') as questions_file:
    questions = json.load(questions_file)

q = []

for question in questions:
    if question['value']:
        question['value'] = int(question['value'][1:].replace(',', ''))
        q.append(question)

result = questions_collection.insert_many(q)
print(result)