"""Remove duplicate song entries in all your playlists.

To reduce churn we try to prefer a duplicate that was retained on previous runs. In order to track the chocies, We maintain a json stash file in STASH_PATH - '~/.playlistsculler' in the originally script configuration.

We depend on gmusicapi being installed:

    https://github.com/simon-weber/Unofficial-Google-Music-API
"""

STASH_PATH = "~/.playlistsculler.json"
# VERBOSE: say much of what's happening while it's happening.
VERBOSE = True
# DRY_RUN True means prospective playlist removals are only reported, not done.
DRY_RUN = False

from gmusicapi import Mobileclient
from getpass import getpass
import json
import sys, os, logging, pprint
from os import path
from copy import copy
from datetime import datetime

class PlaylistsCuller:
    """Cull duplicate track entries from Google Music account's playlists."""

    _api = None                 # The GMusic API instance
    _userId = None
    _playlists = None           # _api.get_all_user_playlist_contents() result
    _plnames_by_id = None       # {playlistId: playlist_name}
    _pldups = None              # {playlistId: {songId: [plEntryId, ...]}}
    # optional _songs_by_id, only for sanity check:
    _songs_by_id = None         # {songId: songMetadata, ...}
    _chosen = {}                # {plId: {songId: trackId}}
    _history = None
    tallies = {}

    def __init__(self, userId=None, password=None):
        if (not userId):
            print "UserId: ",
            userId = sys.stdin.readline().strip()
            self._userId = userId
            password = password or getpass("%s password: " % userId)
        self._api = api = Mobileclient(debug_logging=True,
                                       validate=True,
                                       verify_ssl=True)
        if (not api.login(userId, password)):
            api.logger.error("Login failed")
            raise StandardError("Login failed")
        self._pldups = {}

    def process(self):
        if DRY_RUN:
            print("DRY_RUN - playlist removals inhibited")
        self.fetch_stash()
        self.arrange_playlists_contents()
        self.do_tally('pre')
        try:
            self.do_cull()
        finally:
            self.do_tally('post')
            if not DRY_RUN:
                self.store_stash()
            self.do_report()

    def do_cull(self):
        """Remove playlist's duplicate tracks.

        Prefer to keep track, among duplicates, that has been kept previously.
        """
        doingpl = doingsong = 0
        playlists = self._playlists
        total = len(self._pldups)
        for plId, pldups in self._pldups.items():
            doingpl += 1
            blather("Playlist #%d: %s"
                    % (doingpl, self._plnames_by_id[plId]))
            doingsong = 0
            for songId, entries in pldups.items():
                doingsong += 1
                choice = self.get_chosen(plId, songId)
                if len(entries) > 1:
                    if choice and (choice in entries):
                        entries.remove(choice)
                    else:
                        choice = entries.pop()
                    # Remove remaining entries:
                    if DRY_RUN:
                        residue = entries
                    else:
                        blather("%d " % len(entries), nonewline=True)
                        removed = self._api.remove_entries_from_playlist(
                            entries)
                        if len(removed) != len(entries):
                            residue = [i for i in entries
                                       if i not in set(removed)]
                        else:
                            residue = []
                    if residue:
                        if not DRY_RUN:
                            self._api.logger.warning(
                                "Playlist %s song %s:"
                                " only %d remain for %d requested"
                                % (plId, songId, len(residue),len(entries)))
                        residue.insert(0, choice)
                    else:
                        residue = [choice]
                    # Revise our records to reflect removals:
                    self._pldups[plId][songId] = residue
                elif entries:
                    choice = entries[0]
                if choice:
                    # Register choice whether or not any removals happened -
                    # duplicates may be present next time we run, and we
                    # specifically want to prefer oldest/most stable one.
                    self.register_chosen(plId, songId, choice)
            blather("")

    def get_chosen(self, plId, songId):
        "Return preferred track for playlist plId and song songId, or None."
        if (self._chosen.has_key(plId)
            and self._chosen[plId].has_key(songId)):
            return self._chosen[plId][songId]
        else:
            return None
    def register_chosen(self, plId, songId, trackId):
        """Register trackId as choice for playlist plId and song songId."""
        if self._chosen.has_key(plId):
            self._chosen[plId][songId] = trackId
        else:
            self._chosen[plId] = {songId: trackId}

    def do_report(self):
        pprint.pprint({'pre': self.tallies['pre']})
        pprint.pprint({'post': self.tallies['post']})

    def fetch_stash(self):
        fetched = Stasher(STASH_PATH).fetch_stash() or {'chosen': {},
                                                        'history': []}
        self._history = fetched['history']
        self._chosen = fetched['chosen']
    def store_stash(self):
        self._history.insert(0, (str(datetime.now()), self.tallies))
        Stasher(STASH_PATH).store_stash({'chosen': self._chosen,
                                         'history': self._history})

    def get_playlists(self):
        """Populate self._playlists w/api get_all_user_playlist_contents()."""
        if (not self._playlists):
            blather("Getting playlists... ")
            self._playlists = self._api.get_all_user_playlist_contents()
            blather(" Done.")

    def get_songs(self):
        """Get all songs in self._songs_by_id

        This is optional, just for sanity check."""
        if (not self._songs_by_id):
            blather("Getting songs...")
            songs = incr_getter(self._api.get_all_songs(incremental=True))
            self._songs_by_id = {song[u'id']: song for song in songs}
            blather(" Done.")

    def arrange_playlists_contents(self):
        if (not self._playlists):
            self.get_playlists()
        self._plnames_by_id = {}
        self._pldups = {}
        for pl in self._playlists:
            plId = pl[u'id']
            trackdups = self._pldups[plId] = {}
            self._plnames_by_id[plId] = pl[u'name']
            for track in pl[u'tracks']:
                trId = track[u'trackId']
                if trackdups.has_key(trId):
                    trackdups[trId].append(track[u'id'])
                else:
                    trackdups[trId] = [track[u'id']]

    def do_tally(self, which):
        """Fill tally named 'which' with current playlist number, dup stats.

        Depends on self.arrange_playlists_contents() having been called."""

        tally = self.tallies[which] = {'playlists': 0,
                                       'playlist_tracks': 0,
                                       'playlists_with_dups': 0,
                                       'dups': 0}
        tally['playlists'] = len(self._playlists)
        for pl in self._playlists:
            plId = pl[u'id']
            tally['playlist_tracks'] += len(pl[u'tracks'])
            num_dups = sum([(len(x) - 1)
                            for x in self._pldups[plId].values()])
            if num_dups > 1:
                tally['playlists_with_dups'] += 1
                tally['dups'] += num_dups

    def sanity_check(self):
        """Examine the data to confirm or expose mistaken assumptions."""

        # All playlists are of kind u'sj#playlist':
        blather("Confirming expected user playlists types...")
        self.get_playlists()
        for pl in self._playlists:
            assert pl[u'kind'] == u'sj#playlist'

        # Every track id in plists_dups is a key in self._songs_by_id:
        blather("Confirming all playlist tracks are valid song ids...")
        self.get_songs()
        for apl_dups in self._pldups.values():
            for trId in apl_dups.keys():
                assert self._songs_by_id.has_key(trId)

class Stasher:
    _stash_path = None
    def __init__(self, stash_path):
        """Provide JSON externalization of a data structure to a location.

        The location can include '~' and var references.

        Invalid paths will not be noticed until a write is attempted."""
        self._stash_path = path.expanduser(path.expandvars(stash_path))
    def fetch_stash(self):
        """Return reconstituted data structure, or {} if none yet existing."""
        got = {}
        sf = None
        try:
            sf = open(self._stash_path, 'r')
            got = json.loads(sf.read())
        finally:
            sf and sf.close()
            return got
    def store_stash(self, data):
        """Try to externalize the data in the stash path.

        We pass the exception if the write fails."""
        sf = None
        try:
            sf = open(self._stash_path, 'w')
            json.dump(data, sf, indent=1, separators=(',', ': '))
        finally:
            sf and sf.close()

def incr_getter(generator):
    got = []
    for batch in generator:
        # Might want to accumulate batches and do a single sum at end?
        got += batch
        sys.stdout.write("%d " % len(got))
        sys.stdout.flush()
    return got

def blather(msg, nonewline=False):
    "Print message if in verbose mode."
    if VERBOSE:
        if nonewline:
            sys.stdout.write(msg)
            sys.stdout.flush()
        else:
            print(msg)

if __name__ == "__main__":
    they = PlaylistsCuller()    # Will prompt for username and pw
    they.process()
