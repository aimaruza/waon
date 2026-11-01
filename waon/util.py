
AUDIO_EXTENSIONS = (
    ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma",
)


def format_time(seconds):
    total = int(max(0, seconds))
    minutes, secs = divmod(total, 60)
    return "{}:{:02d}".format(minutes, secs)


def format_duration(seconds):
    total = int(max(0, seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, secs)
    return "{}:{:02d}".format(minutes, secs)


def display_artist(artist, album_artist):
    if album_artist is None:
        return artist
    first = artist.split("/", 1)[0].strip()
    if first.casefold() == album_artist.casefold():
        return album_artist
    return artist


def format_listened(seconds):
    if seconds <= 0:
        return "0 min"
    if seconds < 60:
        return "<1 min"
    return "{:,} min".format(int(seconds // 60))
