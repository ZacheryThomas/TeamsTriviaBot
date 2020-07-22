__author__ = 'Zachery Thomas'

MIN_DATE = '2015-01-01'
MAX_CLUE_VAL = 1000
PREV_CLUE_CACHE = 20

ACCEPTED_CATEGORIES = [
    r'SCIENCE', r'FOOD', r'DRINK', r'GAMES', r'BRAND',
    r'STUPID', r'TECH', r'COMPUTER', r'POURRI',
    r'BIOLOGY', r'ALCOHOL', r'ALSO', r'ANIMAL',
    r'COMPANIES', r'CUISINE',
    r'LOGOS', r'MACHINE', r'SPACE', r'SYMBOLS',
    r'WEATHER', r'WEAPON', r'VEGETABLE', r'BODY',
    r'ANATOMY', r'LETTER WORDS', r'CARTOON', r'FRUIT',
    r'INTERNET', r'MYTH', r'EXERCISE', r'CROSSWORD',
    r'COLOR', r'JAPANESE', r'ITALIAN', r'OLOGY',
]

RIGHT_TEXT = [
    'Yes!',
    'That is correct.',
    'Right on!',
    'That one was tough but you got it!',
    'Correct!',
    'Right!',
    'Good one!'
]

CLOSE_TEXT = [
    'That answer was very close!',
    'That answer was almost correct...',
    'Oooh, so close!',
    'Close guess, but not quite!',
    'Very close! Really close! Extremely close! But not right...'
]

WRONG_TEXT = [
    'Unfortunately that is not correct.',
    'That answer is not correct.',
    'Ooops, thats not right!',
    'Good try! But thats not right.',
    'That is not correct.',
    'Unfortunate...',
    'You fool! you utter nincompoop.',
    'Sorry dumdum, you\'re wrong!'
]