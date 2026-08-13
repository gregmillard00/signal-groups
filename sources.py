"""Source catalogue: public-domain feature films and TV episodes on archive.org.

Every title here is in the US public domain (lapsed copyright / non-renewal), which
is why they are freely redistributable on archive.org. Each entry notes the emotional
register we expect scenes to sit in, purely to guide where we sample clips from - the
actual cluster label for every clip comes from inter1, never from this file.
"""

SOURCES = [
    {
        "key": "notld",
        "identifier": "night-of-the-living-dead-1968_202508",
        "file": "Night of the Living Dead 1968.mp4",
        "title": "Night of the Living Dead",
        "year": 1968,
        "duration": 5717,
        # long basement arguments, panic, people talking over each other
        "sample_from": (600, 5400),
    },
    {
        "key": "carnival",
        "identifier": "CarnivalOfSouls1962",
        "file": "Carnival_of_Souls.mp4",
        "title": "Carnival of Souls",
        "year": 1962,
        "duration": 4940,
        # doctor/landlady conversations, a lot of hedging and unease
        "sample_from": (300, 4600),
    },
    {
        "key": "stranger",
        "identifier": "the-stranger-1946_202511",
        "file": "The Stranger (1946)/The Stranger - 1946.mp4",
        "title": "The Stranger",
        "year": 1946,
        "duration": 5472,
        # Welles: probing interrogation scenes, doubt and deflection
        "sample_from": (300, 5200),
    },
    {
        "key": "johndoe",
        "identifier": "meet-john-doe-1941_202309",
        "file": "Meet John Doe (1941).mp4",
        "title": "Meet John Doe",
        "year": 1941,
        "duration": 7376,
        # Capra: newsroom banter, rallying speeches, declarative delivery
        "sample_from": (300, 7000),
    },
    {
        "key": "doa",
        "identifier": "1950.-d.-o.-a.",
        "file": "1950. D.O.A..mp4",
        "title": "D.O.A.",
        "year": 1950,
        "duration": 5020,
        # noir: a man under extreme time pressure demanding answers
        "sample_from": (200, 4800),
    },
    {
        "key": "dragnet",
        "identifier": "Dragnet_The_Big_False_Make",
        "file": "S03E35_The_Big_False_Make.mp4",
        "title": "Dragnet: The Big False Make",
        "year": 1954,
        "duration": 1579,
        # flat procedural questioning, witnesses hedging
        "sample_from": (60, 1500),
    },
    {
        "key": "hillbillies",
        "identifier": "s01e12_The_Great_Fued_1",
        "file": "s01e12_The_Great_Fued_1.mp4",
        "title": "The Beverly Hillbillies: The Great Feud",
        "year": 1963,
        "duration": 1494,
        # sitcom: broad disagreement, mugging reactions, warm agreement
        "sample_from": (60, 1420),
    },
    # --- Added after the first 90 clips came back badly unbalanced. -------------
    # The films above are noir, horror and procedural, and inter1 read them almost
    # entirely as `stress` (34 detections) and `confidence` (26). Hesitation,
    # disagreement, frustration and confusion barely appeared, so three of the five
    # clusters could not be filled. These three sources were picked for the missing
    # signals specifically: an unscripted quiz show where contestants genuinely
    # stall and hedge on questions, and a comedy built on people bickering.
    {
        "key": "groucho1",
        "identifier": "youtube--7HdOqFxdk8",
        "file": "-7HdOqFxdk8.mp4",
        "title": "You Bet Your Life",
        "year": 1960,
        "duration": 1201,
        # real contestants hesitating and hedging under questioning
        "sample_from": (40, 1150),
    },
    {
        "key": "groucho2",
        "identifier": "youtube-WB5I3WuA8Zs",
        "file": "WB5I3WuA8Zs.mp4",
        "title": "You Bet Your Life",
        "year": 1959,
        "duration": 1358,
        "sample_from": (40, 1300),
    },
    {
        "key": "beatdevil",
        "identifier": "humphrey-bogart-jennifer-jones-comedy-full-movie-beat-the-devil-1953",
        "file": "Humphrey Bogart, Jennifer Jones Comedy Full Movie ｜ Beat The Devil (1953).mp4",
        "title": "Beat the Devil",
        "year": 1953,
        "duration": 5386,
        # ensemble comedy of mutual suspicion: contradiction, needling, exasperation
        "sample_from": (200, 5200),
    },
]

BY_KEY = {s["key"]: s for s in SOURCES}


def download_url(src):
    """Archive.org filenames can contain spaces, parentheses, and non-ASCII
    characters (one here uses a full-width vertical bar), so percent-encode the
    path properly rather than patching individual characters. "/" stays safe
    because some items nest files in subdirectories."""
    from urllib.parse import quote
    ident = src["identifier"]
    return f"https://archive.org/download/{ident}/{quote(src['file'], safe='/')}"


def download_urls(src):
    """All URLs worth trying for one source, best first.

    The /download/ redirector returns HTTP 500 for filenames beginning with a
    hyphen (both You Bet Your Life items are named after their YouTube ids, which
    start with '-'). Fetching the item's assigned storage node directly works
    fine, so fall back to that rather than dropping the source.
    """
    import requests
    from urllib.parse import quote

    urls = [download_url(src)]
    try:
        md = requests.get(
            f"https://archive.org/metadata/{src['identifier']}", timeout=30).json()
        server, d = md.get("server"), md.get("dir")
        if server and d:
            urls.append(f"https://{server}{d}/{quote(src['file'], safe='/')}")
    except Exception:
        pass
    return urls


def credit(src):
    return f"{src['title']} ({src['year']}) - public domain, via archive.org"
