import json


class Config(dict):
    def __init__(self, filename: str, **kwargs):
        with open(filename, "r") as file:
            content = json.load(file)
            self.update(content)

        super().__init__(**kwargs)
