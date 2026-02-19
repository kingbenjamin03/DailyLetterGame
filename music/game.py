"""
Music daily puzzle: show songs, albums, or artists that share a connection,
player guesses the artist, album, genre, or era/decade.

Data is curated and hardcoded (no external API).
Mirrors the structure of movies/game.py.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class MusicCategory:
    key: str           # unique identifier
    label: str         # human-readable answer shown on reveal
    accepted: list[str]  # accepted guess phrases
    difficulty: str    # "easy", "medium", "hard"
    hints: list[str]   # 3 progressive hints
    puzzle_type: str   # "artist" | "album" | "genre" | "era"
    items: list[str]   # clue songs/artists/albums shown to player


DEFAULT_NUM_ITEMS = 6
MIN_ITEMS = 4


def _accept(*phrases: str) -> list[str]:
    # Normalize and dedupe while preserving order.
    out: list[str] = []
    for p in phrases:
        s = " ".join((p or "").strip().lower().split())
        if s and s not in out:
            out.append(s)
    return out


def _hints_for(puzzle_type: str) -> list[str]:
    if puzzle_type == "artist":
        return [
            "These songs or albums share an artist.",
            "They're all by the same musician or band.",
            "Guess the artist or band.",
        ]
    if puzzle_type == "album":
        return [
            "These songs all appear on the same album.",
            "They're tracks from one iconic record.",
            "Guess the album or the artist.",
        ]
    if puzzle_type == "genre":
        return [
            "These artists all share a musical style.",
            "They all belong to the same genre.",
            "Guess the genre.",
        ]
    # era
    return [
        "These artists or songs are from the same time period.",
        "Think about when they were most popular.",
        "Guess the decade (e.g. '1980s').",
    ]


CATEGORIES: list[MusicCategory] = [

    # --- Artist puzzles (show songs → guess artist) ---
    MusicCategory(
        "artist_taylor_swift",
        "Taylor Swift",
        _accept("taylor swift", "swift"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["Shake It Off", "Love Story", "Anti-Hero", "Blank Space", "Bad Blood", "You Belong With Me", "Cruel Summer", "Cardigan"],
    ),
    MusicCategory(
        "artist_the_beatles",
        "The Beatles",
        _accept("the beatles", "beatles"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["Hey Jude", "Let It Be", "Come Together", "Yesterday", "Here Comes the Sun", "Blackbird", "Help!", "A Day in the Life"],
    ),
    MusicCategory(
        "artist_michael_jackson",
        "Michael Jackson",
        _accept("michael jackson", "jackson", "mj"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["Thriller", "Billie Jean", "Beat It", "Smooth Criminal", "Man in the Mirror", "Black or White", "Bad", "Rock with You"],
    ),
    MusicCategory(
        "artist_beyonce",
        "Beyoncé",
        _accept("beyonce", "beyoncé", "bey"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["Crazy in Love", "Halo", "Single Ladies", "Formation", "Irreplaceable", "Lemonade", "Texas Hold 'Em", "Love On Top"],
    ),
    MusicCategory(
        "artist_eminem",
        "Eminem",
        _accept("eminem", "slim shady", "marshall mathers"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["Lose Yourself", "Stan", "Without Me", "The Real Slim Shady", "Rap God", "Not Afraid", "Love the Way You Lie", "Mockingbird"],
    ),
    MusicCategory(
        "artist_bob_dylan",
        "Bob Dylan",
        _accept("bob dylan", "dylan"),
        "medium",
        _hints_for("artist"),
        "artist",
        ["Blowin' in the Wind", "The Times They Are A-Changin'", "Like a Rolling Stone", "Mr. Tambourine Man", "Knockin' on Heaven's Door", "Tangled Up in Blue"],
    ),
    MusicCategory(
        "artist_adele",
        "Adele",
        _accept("adele"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["Rolling in the Deep", "Someone Like You", "Hello", "Skyfall", "Easy On Me", "Set Fire to the Rain", "Chasing Pavements", "When We Were Young"],
    ),
    MusicCategory(
        "artist_drake",
        "Drake",
        _accept("drake", "aubrey graham"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["God's Plan", "Hotline Bling", "One Dance", "Started from the Bottom", "Nice for What", "In My Feelings", "Hold On, We're Going Home", "Passionfruit"],
    ),
    MusicCategory(
        "artist_elvis_presley",
        "Elvis Presley",
        _accept("elvis presley", "elvis", "the king"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["Jailhouse Rock", "Hound Dog", "Blue Suede Shoes", "Love Me Tender", "Suspicious Minds", "Heartbreak Hotel", "Can't Help Falling in Love", "In the Ghetto"],
    ),
    MusicCategory(
        "artist_kendrick_lamar",
        "Kendrick Lamar",
        _accept("kendrick lamar", "kendrick", "k-dot", "kdot"),
        "medium",
        _hints_for("artist"),
        "artist",
        ["HUMBLE.", "Alright", "Swimming Pools", "DNA.", "Money Trees", "i", "Backseat Freestyle", "Not Like Us"],
    ),
    MusicCategory(
        "artist_billie_eilish",
        "Billie Eilish",
        _accept("billie eilish", "billie"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["bad guy", "Happier Than Ever", "Lovely", "Ocean Eyes", "Therefore I Am", "No Time to Die", "when the party's over", "What Was I Made For?"],
    ),
    MusicCategory(
        "artist_kanye_west",
        "Kanye West",
        _accept("kanye west", "kanye", "ye"),
        "easy",
        _hints_for("artist"),
        "artist",
        ["Gold Digger", "Stronger", "All Falls Down", "Flashing Lights", "Runaway", "All of the Lights", "Power", "Heartless"],
    ),

    # --- Album puzzles (show songs → guess album) ---
    MusicCategory(
        "album_thriller",
        "Thriller",
        _accept("thriller", "michael jackson", "jackson", "mj"),
        "easy",
        _hints_for("album"),
        "album",
        ["Thriller", "Billie Jean", "Beat It", "Wanna Be Startin' Somethin'", "Human Nature", "P.Y.T.", "The Girl Is Mine"],
    ),
    MusicCategory(
        "album_abbey_road",
        "Abbey Road",
        _accept("abbey road", "the beatles", "beatles"),
        "medium",
        _hints_for("album"),
        "album",
        ["Come Together", "Something", "Here Comes the Sun", "Oh! Darling", "Octopus's Garden", "You Never Give Me Your Money", "Golden Slumbers"],
    ),
    MusicCategory(
        "album_dark_side_of_the_moon",
        "The Dark Side of the Moon",
        _accept("the dark side of the moon", "dark side of the moon", "dark side", "pink floyd", "floyd"),
        "medium",
        _hints_for("album"),
        "album",
        ["Money", "Time", "Breathe", "The Great Gig in the Sky", "Brain Damage", "Any Colour You Like", "On the Run"],
    ),
    MusicCategory(
        "album_rumours",
        "Rumours",
        _accept("rumours", "rumors", "fleetwood mac", "mac"),
        "medium",
        _hints_for("album"),
        "album",
        ["Go Your Own Way", "The Chain", "Dreams", "Gold Dust Woman", "Don't Stop", "You Make Loving Fun", "Never Going Back Again"],
    ),
    MusicCategory(
        "album_nevermind",
        "Nevermind",
        _accept("nevermind", "nirvana nevermind", "nirvana"),
        "medium",
        _hints_for("album"),
        "album",
        ["Smells Like Teen Spirit", "Come as You Are", "Lithium", "Polly", "Breed", "Territorial Pissings", "Something in the Way"],
    ),
    MusicCategory(
        "album_back_in_black",
        "Back in Black",
        _accept("back in black", "ac dc back in black", "ac/dc", "ac dc", "acdc"),
        "medium",
        _hints_for("album"),
        "album",
        ["Back in Black", "You Shook Me All Night Long", "Hells Bells", "Rock and Roll Ain't Noise Pollution", "Shoot to Thrill", "Have a Drink on Me", "Given the Dog a Bone"],
    ),
    MusicCategory(
        "album_purple_rain",
        "Purple Rain",
        _accept("purple rain", "prince"),
        "medium",
        _hints_for("album"),
        "album",
        ["Purple Rain", "When Doves Cry", "Let's Go Crazy", "I Would Die 4 U", "Baby I'm a Star", "Take Me with U"],
    ),
    MusicCategory(
        "album_lemonade",
        "Lemonade",
        _accept("lemonade", "beyonce lemonade", "beyonce", "beyoncé"),
        "medium",
        _hints_for("album"),
        "album",
        ["Formation", "Hold Up", "Don't Hurt Yourself", "Sorry", "Freedom", "Daddy Lessons", "Love Drought", "All Night"],
    ),
    MusicCategory(
        "album_1989",
        "1989",
        _accept("1989", "taylor swift 1989", "taylor swift", "swift"),
        "easy",
        _hints_for("album"),
        "album",
        ["Shake It Off", "Blank Space", "Style", "Bad Blood", "Out of the Woods", "Wildest Dreams", "How You Get the Girl"],
    ),
    MusicCategory(
        "album_to_pimp_a_butterfly",
        "To Pimp a Butterfly",
        _accept("to pimp a butterfly", "tpab", "kendrick lamar", "kendrick"),
        "hard",
        _hints_for("album"),
        "album",
        ["Alright", "King Kunta", "The Blacker the Berry", "i", "Wesley's Theory", "Complexion", "These Walls"],
    ),

    # --- Genre puzzles (show artists → guess genre) ---
    MusicCategory(
        "genre_jazz",
        "Jazz",
        _accept("jazz"),
        "medium",
        _hints_for("genre"),
        "genre",
        ["Miles Davis", "John Coltrane", "Louis Armstrong", "Ella Fitzgerald", "Duke Ellington", "Charlie Parker", "Thelonious Monk", "Billie Holiday"],
    ),
    MusicCategory(
        "genre_classic_rock",
        "Classic Rock",
        _accept("classic rock", "rock", "hard rock"),
        "easy",
        _hints_for("genre"),
        "genre",
        ["Led Zeppelin", "The Rolling Stones", "The Who", "Jimi Hendrix", "Pink Floyd", "Cream", "Aerosmith", "The Doors"],
    ),
    MusicCategory(
        "genre_hip_hop",
        "Hip-Hop",
        _accept("hip-hop", "hip hop", "rap", "rap music"),
        "easy",
        _hints_for("genre"),
        "genre",
        ["Jay-Z", "Nas", "Tupac", "The Notorious B.I.G.", "Wu-Tang Clan", "Rakim", "Biggie", "Public Enemy"],
    ),
    MusicCategory(
        "genre_country",
        "Country",
        _accept("country", "country music"),
        "easy",
        _hints_for("genre"),
        "genre",
        ["Johnny Cash", "Dolly Parton", "Willie Nelson", "Garth Brooks", "Hank Williams", "Shania Twain", "Waylon Jennings", "Patsy Cline"],
    ),
    MusicCategory(
        "genre_classical",
        "Classical Music",
        _accept("classical", "classical music"),
        "easy",
        _hints_for("genre"),
        "genre",
        ["Beethoven", "Mozart", "Bach", "Chopin", "Vivaldi", "Brahms", "Handel", "Schubert"],
    ),
    MusicCategory(
        "genre_pop",
        "Pop",
        _accept("pop", "pop music"),
        "easy",
        _hints_for("genre"),
        "genre",
        ["Katy Perry", "Justin Bieber", "Ariana Grande", "Bruno Mars", "Selena Gomez", "Ed Sheeran", "Charlie Puth", "Dua Lipa"],
    ),
    MusicCategory(
        "genre_r_and_b",
        "R&B",
        _accept("r&b", "r and b", "rnb", "rhythm and blues", "soul"),
        "medium",
        _hints_for("genre"),
        "genre",
        ["Marvin Gaye", "Stevie Wonder", "Whitney Houston", "Aretha Franklin", "Usher", "Alicia Keys", "Mary J. Blige", "John Legend"],
    ),
    MusicCategory(
        "genre_punk",
        "Punk Rock",
        _accept("punk rock", "punk"),
        "hard",
        _hints_for("genre"),
        "genre",
        ["The Ramones", "Sex Pistols", "The Clash", "Buzzcocks", "Dead Kennedys", "Black Flag", "The Damned", "Bad Brains"],
    ),

    # --- Era puzzles (show artists → guess decade) ---
    MusicCategory(
        "era_1960s",
        "1960s",
        _accept("1960s", "the 60s", "60s", "nineteen sixties"),
        "easy",
        _hints_for("era"),
        "era",
        ["The Beatles", "The Rolling Stones", "Bob Dylan", "The Beach Boys", "Simon & Garfunkel", "The Doors", "Jimi Hendrix", "Joni Mitchell"],
    ),
    MusicCategory(
        "era_1970s",
        "1970s",
        _accept("1970s", "the 70s", "70s", "nineteen seventies"),
        "medium",
        _hints_for("era"),
        "era",
        ["Led Zeppelin", "Fleetwood Mac", "ABBA", "David Bowie", "Elton John", "Stevie Wonder", "Donna Summer", "The Eagles"],
    ),
    MusicCategory(
        "era_1980s",
        "1980s",
        _accept("1980s", "the 80s", "80s", "nineteen eighties"),
        "easy",
        _hints_for("era"),
        "era",
        ["Michael Jackson", "Prince", "Madonna", "Bruce Springsteen", "Whitney Houston", "U2", "Cyndi Lauper", "Guns N' Roses"],
    ),
    MusicCategory(
        "era_1990s",
        "1990s",
        _accept("1990s", "the 90s", "90s", "nineteen nineties"),
        "easy",
        _hints_for("era"),
        "era",
        ["Nirvana", "Pearl Jam", "Tupac", "The Notorious B.I.G.", "TLC", "Backstreet Boys", "Spice Girls", "Alanis Morissette"],
    ),
    MusicCategory(
        "era_2000s",
        "2000s",
        _accept("2000s", "the 2000s", "two thousands", "00s", "aughts"),
        "medium",
        _hints_for("era"),
        "era",
        ["Eminem", "Beyoncé", "Jay-Z", "Kanye West", "OutKast", "Nelly", "Usher", "Alicia Keys"],
    ),
    MusicCategory(
        "era_2010s",
        "2010s",
        _accept("2010s", "the 2010s", "twenty tens", "tens"),
        "easy",
        _hints_for("era"),
        "era",
        ["Adele", "Drake", "Kendrick Lamar", "Taylor Swift", "Bruno Mars", "Ed Sheeran", "Cardi B", "Post Malone"],
    ),
]


def _load_approved_suggestions() -> list[MusicCategory]:
    """Load approved user-submitted puzzles from data/suggestions.json."""
    path = Path(__file__).resolve().parent.parent / "data" / "suggestions.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            all_sug = json.load(f)
        result = []
        for s in all_sug:
            if s.get("category") == "music" and s.get("status") == "approved":
                items = s.get("items", [])
                if len(items) < MIN_ITEMS:
                    continue
                result.append(MusicCategory(
                    key=s.get("id", "user_suggestion"),
                    label=s.get("label", ""),
                    accepted=s.get("accepted", [s.get("label", "").lower()]),
                    difficulty=s.get("difficulty", "medium"),
                    hints=s.get("hints", ["These items share a connection.", "Think about what links them.", "Guess the connection."]),
                    puzzle_type=s.get("puzzle_type", "user"),
                    items=items,
                ))
        return result
    except Exception:
        return []


def get_today_puzzle() -> dict | None:
    """Deterministic puzzle for today based on date seed."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(today)
    return _pick_puzzle(rng)


def get_random_puzzle() -> dict | None:
    """Random puzzle."""
    return _pick_puzzle(random.Random())


def _pick_puzzle(rng: random.Random) -> dict | None:
    """Pick a category and sample clue items."""
    cats = list(CATEGORIES) + _load_approved_suggestions()
    rng.shuffle(cats)
    for cat in cats:
        if len(cat.items) < MIN_ITEMS:
            continue
        n = min(DEFAULT_NUM_ITEMS, len(cat.items))
        words = rng.sample(cat.items, n)
        return {
            "words": words,
            "rule": cat.label,
            "hints": cat.hints,
            "difficulty": cat.difficulty,
            "category_key": cat.key,
        }
    return None


def check_music_guess(guess: str, rule: str, category_key: str = "") -> tuple[bool, str]:
    """Check user guess against the music rule. Keyword/phrase matching."""
    g = (guess or "").strip().lower()
    if not g:
        return False, "Type your guess first."

    normalized = " ".join(g.split())
    rule_lower = (rule or "").strip().lower()

    if rule_lower and (rule_lower in normalized or normalized in rule_lower):
        return True, "Correct!"

    cat = None
    for c in CATEGORIES:
        if c.key == category_key or c.label == rule:
            cat = c
            break

    if cat:
        for phrase in cat.accepted:
            if phrase in normalized or normalized in phrase:
                return True, "Correct!"

    return False, "Not quite. Think about what these songs or artists have in common."
