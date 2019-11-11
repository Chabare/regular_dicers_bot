from datetime import datetime
from typing import Dict, Optional

from graphqlclient import GraphQLClient


def add_event() -> Optional[Dict]:
    client = GraphQLClient('https://partyamt.carstens.tech/graphql')

    i = '''
    mutation {
      addEvent(input:{title:"Würfeln",time:{{timestamp}},location:{name:"Kasinostr. 5, Darmstadt"},partyamtId:0,url:"https://www.enchilada.de",description:"awesome possum",icsLink:"", mapsLink:"https://www.google.com/maps/place/Kasinostra%C3%9Fe+5,+64293+Darmstadt/@49.8726113,8.6423045,17z/data=!3m1!4b1!4m5!3m4!1s0x47bd708841ee43a5:0x5629d5367ee8115e!8m2!3d49.8726113!4d8.6444985",tags:[]}) {
        id
      }
    }
    '''.replace("{{timestamp}}", str(int(datetime.now().replace(hour=22, minute=0).timestamp())))

    # TODO: find out what this throws, probably URLError
    # noinspection PyBroadException
    try:
        return client.execute(i)
    except Exception:
        pass
