"""Remove duplicate song entries in all your playlists.

To reduce churn we try to prefer a duplicate that was retained on previous runs. In order to track the chocies, We maintain a json stash file in STASH_PATH - '~/.playlistsculler' in the originally script configuration.

We depend on gmusicapi being installed:

    https://github.com/simon-weber/Unofficial-Google-Music-API
"""

STASH_PATH = "~/.playlistsculler"
# VERBOSE: say much of what's happening while it's happening.
VERBOSE = True
# DRY_RUN True means prospective playlist removals are only reported, not done.
DRY_RUN = True

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
    _pldups = None              # {plylistId: {songId: [plEntryId, ...]}}
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
        self.sort_playlists_contents()
        self.do_tally('pre')
        self.do_cull()
        self.do_tally('post')
        self.store_stash()
        self.do_report()

    def do_cull(self):
        """Remove playlist's duplicate tracks.

        Prefer to keep track, among duplicates, that has been kept previously.
        """
        did = 0
        total = len(self._pldups)
        for plId, pldups in self._pldups.items():
            if not did % 100:
                blather("did %d of %d" % (did, total))
            did += 1
            for songId, entries in pldups.items():
                choice = self.get_chosen(plId, songId)
                if len(entries) > 1:
                    if choice and (choice in entries):
                        entries.remove(choice)
                    else:
                        choice = entries.pop()
                    # Remove remaining entries:
                    if DRY_RUN:
                        residue = entries
                        #blather("Playlist %s song %s: %d removals pending"
                        #        % (plId, songId, len(entries)))
                    else:
                        blather("%d: Removing %d tracks..."
                                % (did, len(entries)))
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
                    self._pldups[plId][songId] = residue
                elif entries:
                    choice = entries[0]
                if choice:
                    # Register choice whether or not any removals happened -
                    # duplicates may be present next time we run, and we
                    # specifically want to prefer oldest/most stable one.
                    self.register_chosen(plId, songId, choice)

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

    def sort_playlists_contents(self):
        if (not self._playlists):
            self.get_playlists()
            for pl in self._playlists:
                plid = pl[u'id']
                trackdups = self._pldups[plid] = {}
                for track in pl[u'tracks']:
                    trid = track[u'trackId']
                    if trackdups.has_key(trid):
                        trackdups[trid].append(track[u'id'])
                    else:
                        trackdups[trid] = [track[u'id']]

    def do_tally(self, which):
        """Fill tally named 'which' with current playlist number, dup stats.

        Depends on self.sort_playlists_contents() having been called."""

        tally = self.tallies[which] = {'playlists': 0,
                                       'playlist_tracks': 0,
                                       'playlists_with_dups': 0,
                                       'dups': 0}
        tally['playlists'] = len(self._playlists)
        for pl in self._playlists:
            plid = pl[u'id']
            tally['playlist_tracks'] += len(pl[u'tracks'])
            num_dups = len(self._pldups[plid])
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
            for trid in apl_dups.keys():
                assert self._songs_by_id.has_key(trid)

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
            json.dump(data, sf)
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

def blather(msg):
    "Print message if in verbose mode."
    if VERBOSE:
        print(msg)

if __name__ == "__main__":
    they = PlaylistsCuller()    # Will prompt for username and pw
    they.process()
