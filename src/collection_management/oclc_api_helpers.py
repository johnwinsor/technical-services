from bookops_worldcat import WorldcatAccessToken, MetadataSession
from time import sleep

def getToken():

    token = WorldcatAccessToken(
        key="ah7cfWMHiiFQA2KL5DhmgQzJiUcPFxauH9x04JYcqqgrNeOBplFhN73zbF2BAYKYobEs5J0KqY6iiMzf",
        secret="B6Y/rarweIqSpyrIK+THTWUSZ5pJLpgY",
        scopes="WorldCatMetadataAPI",
    )
    return token

def getSession(token):
    # Create a SearchSession object
    session = MetadataSession(authorization=token)
    return session

def getBriefBib(oclc_number, session):
    sleep(0.5)
    with session:
        response = session.brief_bibs_get(oclc_number)
        briefBib = response.json()
    return briefBib

def holdingsUnset(oclc_number, session):
    sleep(0.5)
    with session:
        response = session.holdings_unset(oclcNumber=oclc_number)
        success = response.json()['success']
        if success:
            print(f"{oclc_number}: {response.json()['message']}")
            return response.json()
        else:
            print(f"ERROR UNSETTING HOLDING FOR {oclc_number}")
            return None

if __name__ == "__main__":
    oclc_number = '1110469890'
    briefBib = getBriefBib(oclc_number)
    print(briefBib)
    holdingsUnset(oclc_number)