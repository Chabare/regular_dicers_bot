import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, List

from graphqlclient import GraphQLClient


@dataclass
class Ingredient:
    name: str

    @classmethod
    def from_dict(cls, json_element: Dict) -> "Ingredient":
        return cls(json_element.get("name"))

    def __str__(self):
        return self.name


@dataclass
class Cocktail:
    name: str
    jumbo: bool
    alcoholic: bool
    ingredients: List[Ingredient]

    @classmethod
    def from_dict(cls, json_element: Dict) -> "Cocktail":
        ingredients = [Ingredient.from_dict(d) for d in json_element.get("ingredients")]
        return cls(json_element.get("name"), json_element.get("jumbo"), json_element.get("alcoholic"), ingredients)

    def __str__(self) -> str:
        jumbo = "(Jumbo)" if self.jumbo else ""
        alcoholic = "💔" if not self.alcoholic else ""
        ingredients = "(" + ", ".join(map(str, self.ingredients)) + ")"

        return " ".join([self.name, jumbo, alcoholic, ingredients])


def get_cocktails() -> Optional[List[Cocktail]]:
    client = GraphQLClient('http://localhost:8000/graphql')  # TODO

    i = '''
    {
      cocktails {
        name
        jumbo
        alcoholic
        ingredients {
            name
        }
      }
    }
    '''

    # TODO: find out what this throws, probably URLError
    # noinspection PyBroadException
    try:
        result = json.loads(client.execute(i))
        if result.get("errors"):
            return None

        return [Cocktail.from_dict(d) for d in result.get("data", {}).get("cocktails", [])]
    except Exception as e:
        pass
