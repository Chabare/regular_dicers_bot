import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, List

from graphqlclient import GraphQLClient


@dataclass
class Cocktail:
    name: str
    jumbo: bool
    alcoholic: bool

    @classmethod
    def from_dict(cls, json_element: Dict) -> "Cocktail":
        return Cocktail(json_element.get("name"), json_element.get("jumbo"), json_element.get("alcoholic"))

    def __str__(self) -> str:
        jumbo = "(Jumbo)" if self.jumbo else ""
        alcoholic = "💔" if not self.alcoholic else ""

        return " ".join([self.name, jumbo, alcoholic])


def get_cocktails() -> Optional[List[Cocktail]]:
    client = GraphQLClient('https://rd-backend.carstens.tech/graphql')

    i = '''
    {
      cocktails {
        name
        jumbo
        alcoholic
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
