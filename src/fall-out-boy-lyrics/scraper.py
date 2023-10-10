import argparse
import json
import socket
import lyricsgenius
import math
import pandas as pd
import re
import requests
from lyricsgenius.types import Song
from local import *

ALBUMS = [
   'Fall Out Boys Evening Out With Your Girlfriend', 'Take This To Your Grave', 
   'My Heart Will Always Be the B-Side to My Tongue', 'From Under The Cork Tree', 
   'Infinity on High', 'Welcome to the New Administration', 'Folie a Deux',
   'Believers Never Die vol 1', 'Save Rock and Roll', 'PAX AM Days', 
   'American Beauty/American Psycho', 'Make America Psycho Again', 'Mania', 'Llamania',
   'Lake Effect Kid', 'Believers Never Die vol 2', 'So Much (For) Stardust'
]

# Songs that don't have an album or for which Fall Out Boy is not the primary artist
OTHER_SONGS = [
    'One and Only', 'One of Those Nights', 'Back to Earth', 
    'Stayin Out All Night (Boys of the Zummer Remix)', 'Ive Been Waiting',
    'Summer Days', 'Hand Crushed by a Mallet', 'Electric Touch (Taylors Version) (From the Vault)',
    '7-9 Legendary (Blink and Youll Miss It)', 'Guilty As Charged (Tell Hip Hop Im Literate)',
    'Hand of God', 'Dance, Dance (demo)', 'Austin, We Have A Problem', 'Star 67',
    'We Dont Take Hits, We Write Them', 'Fellowship of the Nerd', 'My Songs Know What You Did In The Dark (demo)',
    'Bronxs Lullabye', 'This Aint A Scene, Its An Arms Race (Kanye West Remix)', 'Irresistible (feat. Demi Lovato)',
    '"Ghostbusters (Im Not Afraid) (from the Ghostbusters Original Motion Picture Soundtrack)"', 
    'Champion (Remix) (feat. RM)'
]

# Songs for which there is trouble retrieving them by name - some of these are probably no longer an issue anyways
EXTRA_SONG_API_PATHS = {
    
}

# Songs that are somehow duplicates / etc.
IGNORE_SONGS = [
    
]

ARTIST_ID = 1177
API_PATH = "https://api.genius.com"
ARTIST_URL = API_PATH + "/artists/" + str(ARTIST_ID)
CSV_PATH = 'songs.csv'
LYRIC_PATH = 'lyrics.csv'
LYRIC_JSON_PATH = 'lyrics.json'
SONG_LIST_PATH = 'song_titles.txt'


def main():
    parser = argparse.ArgumentParser()
    # Only look for songs that aren't already existing
    parser.add_argument('--append', action='store_true')
    # Append songs specifically in EXTRA_SONG_API_PATHS
    parser.add_argument('--appendpaths', action='store_true')
    args = parser.parse_args()
    existing_df, existing_songs = None, []
    if args.append or args.appendpaths:
        existing_df = pd.read_csv(CSV_PATH)
        existing_songs = list(existing_df['Title'])
    genius = lyricsgenius.Genius(access_token)
    songs = get_songs() if not args.appendpaths else []
    songs_by_album, has_failed, last_song = {}, True, ''
    while has_failed:
        songs_by_album, has_failed, last_song = sort_songs_by_album(genius, songs, songs_by_album, last_song, existing_songs)
    albums_to_songs_csv(songs_by_album, existing_df)
    songs_to_lyrics()
    lyrics_to_json()


def get_songs():
    print('Getting songs...')
    songs = []
    next_page = 1
    while next_page != None:
        request_url = ARTIST_URL + "/songs?page=" + str(next_page)
        r = requests.get(request_url,
                         headers={'Authorization': "Bearer " + access_token})
        song_data = json.loads(r.text)
        songs.extend(song_data['response']['songs'])
        next_page = song_data['response']['next_page']
    returned_songs = []
    for song in songs:
        if song['primary_artist']['id'] == ARTIST_ID or song['title'] in OTHER_SONGS:
            returned_songs.append(song)
    return returned_songs


def sort_songs_by_album(genius, songs, songs_by_album, last_song, existing_songs=[]):
    def get_song_data(api_path):
        request_url = API_PATH + api_path
        r = requests.get(request_url,
                         headers={'Authorization': "Bearer " + access_token})
        return json.loads(r.text)['response']['song']

    def clean_lyrics_and_append(song_data, album_name, lyrics, songs_by_album):
        cleaned_lyrics = clean_lyrics(lyrics)
        s = Song(genius, song_data, cleaned_lyrics)
        if album_name not in songs_by_album:
            songs_by_album[album_name] = []
        songs_by_album[album_name].append(s)

    print('Sorting songs by album...')
    songs_so_far = []
    for song in songs:
        lyrics = None
        if song['title'] > last_song and song['title'] not in existing_songs and song[
                'title'] not in IGNORE_SONGS:
            try:
                song_data = get_song_data(song['api_path'])
                if song_data != None and 'album' in song_data and song_data[
                        'lyrics_state'] == 'complete':
                    album_name = song_data['album']['name'].strip(
                    ) if song_data['album'] else None
                    # Handle special cases -- uncategorized songs are under "Taylor Swift " on Genius
                    if album_name == "Taylor Swift" and album_name != song_data[
                            'album']['name']:
                        album_name = "Uncategorized"
                    if album_name is None:
                        album_name = ""
                    lyrics = genius.lyrics(song_id=song_data['id'])
                    # Ensure that there are lyrics
                    if lyrics and has_song_identifier(lyrics) and (
                            album_name or (song['title'] in OTHER_SONGS)):
                        songs_so_far.append(song['title'])
                        clean_lyrics_and_append(song_data, album_name, lyrics,
                                                songs_by_album)
            except requests.exceptions.Timeout or socket.timeout:
                print('Failed receiving song', song['title'],
                      '-- saving songs so far')
                return songs_by_album, True, song['title']

    for api_path in EXTRA_SONG_API_PATHS:
        song_data = get_song_data(api_path)
        if song_data['title'] not in existing_songs and song_data['title'] not in songs_so_far:
            lyrics = genius.lyrics(song_id=song_data['id'])
            album_name = EXTRA_SONG_API_PATHS[api_path]
            clean_lyrics_and_append(song_data, album_name, lyrics,
                                    songs_by_album)

    return songs_by_album, False, ''


def albums_to_songs_csv(songs_by_album, existing_df=None):
    print('Saving songs to CSV...')
    songs_records = []
    songs_titles = []
    for album in songs_by_album:
        if album in ALBUMS:
            for song in songs_by_album[album]:
                if song.title not in IGNORE_SONGS and song.title not in songs_titles:
                    record = {
                        'Title': song.title.strip('\u200b'),
                        'Album':
                        album if 'Lover (Target' not in album else 'Lover',
                        'Lyrics': song.lyrics,
                    }
                    songs_records.append(record)
                    songs_titles.append(song.title)
        else:
            for song in songs_by_album[album]:
                if song in OTHER_SONGS and song.title not in songs_titles:
                    record = {
                        'Title': song.title,
                        'Album': album,
                        'Lyrics': song.lyrics,
                    }
                    songs_records.append(record)
                    songs_titles.append(song.title)

    song_df = pd.DataFrame.from_records(songs_records)
    if existing_df is not None:
        existing_df = existing_df[existing_df['Album'].isin(ALBUMS)]
        song_df = pd.concat([existing_df, song_df])
        song_df = song_df[~song_df['Title'].isin(IGNORE_SONGS)]
        song_df = song_df.drop_duplicates('Title', keep="last")
    song_df.to_csv(CSV_PATH, index=False)


def has_song_identifier(lyrics):
    if '[Intro' in lyrics or '[Verse' in lyrics or '[Chorus' in lyrics:
        return True
    return False

class Lyric:
    def __init__(self, lyric, prev_lyric=None, next_lyric=None):
        self.lyric = lyric
        self.prev = prev_lyric
        self.next = next_lyric

    def __eq__(self, other):
        return self.lyric == other.lyric and self.prev == other.prev and self.next == other.next

    def __repr__(self):
        return self.lyric

    def __hash__(self):
        return hash((self.prev or "") + self.lyric + (self.next or ""))


def songs_to_lyrics():
    print('Generating lyrics CSV...')
    song_data = pd.read_csv(CSV_PATH)
    lyric_records = []
    song_titles = []
    for song in song_data.to_records(index=False):
        title, album, lyrics = song
        if title not in song_titles:
            song_titles.append(title)
            lyric_dict = get_lyric_list(lyrics)
            for lyric in lyric_dict:
                lyric_record = {
                    'Song': title,
                    'Album': album,
                    'Lyric': lyric.lyric,
                    'Previous Lyric': lyric.prev,
                    'Next Lyric': lyric.next,
                    'Multiplicity': lyric_dict[lyric]
                }
                lyric_records.append(lyric_record)
    lyric_df = pd.DataFrame.from_records(lyric_records)
    lyric_df.to_csv(LYRIC_PATH, index=False)
    # Writing song list to make it easy to compare changes
    with open(SONG_LIST_PATH, 'w') as f:
        f.write('\n'.join(sorted(set(song_titles))))
        f.close()


def get_lyric_list(lyrics):
    line = None
    lines = lyrics.split('\n')
    lyric_dict = {}
    for i in range(len(lines)):
        curr_line = lines[i].strip()
        if len(curr_line) > 0 and curr_line[0] != '[':
            prev_line = line
            line = curr_line
            next_line = lines[i + 1] if i + 1 < len(lines) and len(
                lines[i + 1]) > 0 and lines[i + 1][0] != '[' else None
            lyric = Lyric(line, prev_line, next_line)
            if lyric not in lyric_dict:
                lyric_dict[lyric] = 1
            else:
                lyric_dict[lyric] = lyric_dict[lyric] + 1
        # If there is a chorus / etc. indicator then set current line to "None"
        # if the previous line was not already set
        elif line is not None:
            line = None
    return lyric_dict


def lyrics_to_json():
    print('Generating lyrics JSON...')
    lyric_dict = {}
    lyric_data = pd.read_csv(LYRIC_PATH)
    for lyric in lyric_data.to_records(index=False):
        title, album, lyric, prev_lyric, next_lyric, multiplicity = lyric
        if album != album: # handling for NaN
            album = title
        if album not in lyric_dict:
            lyric_dict[album] = {}
        if title not in lyric_dict[album]:
            lyric_dict[album][title] = []
        lyric_dict[album][title].append({
            'lyric':
            lyric,
            'prev':
            "" if prev_lyric != prev_lyric else prev_lyric,  # replace NaN
            'next':
            "" if next_lyric != next_lyric else next_lyric,
            'multiplicity':
            int(multiplicity),
        })
    lyric_json = json.dumps(lyric_dict, indent=4)
    with open(LYRIC_JSON_PATH, 'w') as f:
        f.write(lyric_json)
        f.close()


def clean_lyrics(lyrics: str) -> str:
    # Remove first line (title + verse line)
    lyrics = lyrics.split(sep='\n', maxsplit=1)[1]
    # Replace special quotes with normal quotes
    lyrics = re.sub(r'\u2018|\u2019', "'", lyrics)
    lyrics = re.sub(r'\u201C|\u201D', '"', lyrics)
    # Replace special unicode spaces with standard space
    lyrics = re.sub(
        r'[\u00A0\u1680​\u180e\u2000-\u2009\u200a​\u200b​\u202f\u205f​\u3000]',
        " ", lyrics)
    # Replace dashes with space and single hyphen
    lyrics = re.sub(r'\u2013|\u2014', " - ", lyrics)
    # Replace hyperlink text
    lyrics = re.sub(r"[0-9]*URLCopyEmbedCopy", '', lyrics)
    lyrics = re.sub(r"[0-9]*Embed", '', lyrics)
    lyrics = re.sub(r"[0-9]*EmbedShare", '', lyrics)
    lyrics = re.sub(r"See [\w\s]* LiveGet tickets as low as \$\d*You might also like", '\n', lyrics)

    return lyrics


if __name__ == '__main__':
    main()
