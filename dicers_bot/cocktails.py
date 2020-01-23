import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List

from graphqlclient import GraphQLClient

from .logger import create_logger


@dataclass
class Ingredient:
    name: str

    @classmethod
    def from_dict(cls, json_element: Dict) -> "Ingredient":
        return cls(json_element.get("name"))

    def __str__(self):
        return f"_{self.name}_"


@dataclass
class Cocktail:
    id: int
    name: str
    jumbo: bool
    alcoholic: bool
    category: str
    ingredients: List[Ingredient]

    @classmethod
    def from_dict(cls, json_element: Dict) -> "Cocktail":
        ingredients = [Ingredient.from_dict(d) for d in json_element.get("ingredients")]
        return cls(int(json_element.get("id")), json_element.get("name"), json_element.get("jumbo"), json_element.get("alcoholic"), json_element.get("category"), ingredients)

    def __str__(self) -> str:
        jumbo = "(Jumbo)" if self.jumbo else ""
        alcoholic = "💔" if not self.alcoholic else ""
        ingredients = "(" + ", ".join(map(str, self.ingredients)) + ")"

        return " ".join([f"*{self.name}*", jumbo, alcoholic, ingredients])


@lru_cache(maxsize=None)
def get_cocktails() -> List[Cocktail]:
    logger = create_logger("get_cocktails")
    logger.debug("Start")

    client = GraphQLClient('https://rd-backend.carstens.tech/graphql')
    # client = GraphQLClient('http://localhost:8000/graphql')

    i = '''
    {
      cocktails {
        id
        name
        jumbo
        alcoholic
        category
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
        errors = result.get("errors")
        if errors:
            logger.error(f"Couldn't fetch cocktails: {errors}")
            return []

        return [Cocktail.from_dict(d) for d in result.get("data", {}).get("cocktails", [])]
    except Exception:
        logger.error(f"Couldn't fetch cocktails", exc_info=True)
        return []
