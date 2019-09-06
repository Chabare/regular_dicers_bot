import random

from typing import List


class Insult:
    FILENAME = "insults"
    cache = list()

    def __init__(self, text: str):
        self.text = text

    @staticmethod
    def read_all() -> List["Insult"]:
        with open(Insult.FILENAME) as file:
            insults = [Insult(line.strip()) for line in file.readlines() if line.strip()]
            Insult.cache = insults

            return insults

    @classmethod
    def random(cls) -> "Insult":
        insults = Insult.read_all()

        return insults[random.randint(0, len(insults) - 1)]

    @staticmethod
    def add(text: str) -> bool:
        if not Insult.cache:
            Insult.cache = Insult.read_all()

        if text not in [insult.text for insult in Insult.cache]:
            Insult.cache.append(Insult(text))
            with open(Insult.FILENAME, "a+") as file:
                file.writelines("\n" + text)

            return True

        return False
