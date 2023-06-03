import random
import uuid
from collections import namedtuple

DFAULT_REFUSAL_MESSAGE = "no."
MODE_INT_TO_STRING = {
    1: 'Single Elimination',
    2: 'Double Elimination'
}
GENDER_INT_TO_STRING = {
    0: "😐",
    1: "🚹",
    2: "🚺",
    3: "🚁"
}

FlashCategories = namedtuple('flash_type', ['message', 'error', 'warning', 'success'])
STYLE = FlashCategories('primary', 'danger', 'warning', 'success')

LAST_NAMES = ("Einstein", "Newton", "Darwin", "Hawking", "Curie", "Tesla", "Galileo", "Mendel", "Kepler", "Copernicus",
              "Feynman", "Bohr", "Pasteur", "Fleming", "Watson", "Franklin", "Hubble", "Planck", "Heisenberg", "Euler",
              "Gauss", "Euclid", "Ramanujan", "Fermat", "Turing", "Hilbert", "Descartes", "Gödel", "Archimedes",
              "Poincaré", "Cantor", "Leibniz", "Galois", "Pascal", "Laplace", "Fibonacci", "Knuth", "Dijkstra",
              "Berners - Lee", "McCarthy", "von Neumann", "Backus", "Engelbart", "Ritchie", "Liskov", "Cerf", "Wozniak",
              "Kay", "Hopper", "Lovelace", "Lamport", "Stallman", "Brin", "Page", "Carmack", "Socrates", "Plato",
              "Pythagoras", "Epicurus", "Diogenes", "Zeno", "Parmenides", "Protagoras", "Empedocles", "Anaximander",
              "Xenophanes", "Thales", "Heraclitus", "Democritus", "Aristotle", "Proclus", "Plotinus",)

GERUNDS = ("Swimming", "Running", "Reading", "Writing", "Dancing", "Singing", "Cooking", "Painting", "Playing",
           "Sleeping", "Eating", "Laughing", "Traveling", "Studying", "Working", "Hiking", "Cycling", "Gardening",
           "Shopping", "Listening", "Talking", "Dreaming", "Drawing", "Exercising", "Meditating", "Volunteering",
           "Crafting", "Knitting", "Designing", "Teaching", "Learning", "Organizing", "Exploring", "Sailing", "Scuba",
           "Diving", "Surfing", "Skiing", "Snorkeling", "Photographing", "Acting", "Socializing", "Networking",
           "Blogging", "Programming", "Researching", "Filming", "Editing", "Collaborating", "Creating", "Helping",)

EMOJIS = ("😄", "🌟", "🍕", "🎉", "🌺", "🐶", "📚", "🎈", "🌞", "🍦", "🎵", "🏀", "🌈", "🚀", "🍓", "🎁", "🐱", "🌼", "🍔", "🎮", "🌸", "🍩",
          "🎸", "🏝️", "🚲", "🍿", "📷", "🍀", "🍔", "⚽️", "🌍", "🎡", "🍹", "📺", "🌲", "🍁", "🎤", "🐠", "🌙", "🍭", "🚗", "🎨", "🍉",
          "📝", "🍂", "🎯", "🌵", "📱", "🍇", "🎃",)


def generate_name() -> str:
    # select random LAST_NAME
    last_name = random.choice(LAST_NAMES)
    # select random GERUND
    gerund = random.choice(GERUNDS)
    # select random EMOJI
    emoji = random.choice(EMOJIS)
    return f"{gerund} {last_name} {emoji}"


def generate_token() -> str:
    return uuid.uuid4().hex[:12]
