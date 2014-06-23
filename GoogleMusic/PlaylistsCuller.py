"""Remove duplicate song entries in all your playlists.

To reduce churn we try to prefer a duplicate that was retained on previous runs. In order to track the chocies, We maintain a json stash file in STASH_PATH - '~/.playlistsculler' in the originally script configuration.

We depend on gmusicapi being installed:

    https://github.com/simon-weber/Unofficial-Google-Music-API
"""

STASH_PATH = "~/.playlistsculler"

from gmusicapi import Mobileclient
from getpass import getpass
import json
import sys, os
from os import path

class PlaylistsCuller:
    """Cull duplicate track entries from Google Music account's playlists."""

    _api = None                 # The GMusic API instance
    _userId = None
    _plcontents = None          # _api.get_all_user_playlist_contents() result
    _pllsts_dups = None         # {plylistId: {songId: [plEntryId, ...]}}
    # _songs_by_id is optional, used just for sanity check:
    _songs_by_id = None         # {songId: songMetadata, ...}

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
        self._pllsts_dups = {}

    def get_playlists(self):
        if (not self._plcontents):
            print "Getting playlists... "
            self._plcontents = self._api.get_all_user_playlist_contents()
            print " Done."

    def get_songs(self):
        """Get all songs in self._songs_by_id

        This is optional, just for sanity check."""
        if (not self._songs_by_id):
            print "Getting songs..."
            songs = incr_getter(self._api.get_all_songs(incremental=True))
            self._songs_by_id = {song[u'id']: song for song in songs}
            print " Done."

    def sort_playlists_contents(self):
        if (not self._plcontents):
            self.get_playlists_contents()
            for pl in self._plcontents:
                plid = pl[u'id']
                plduptracks = self._pllsts_dups[plid] = {}
                for track in pl[u'tracks']:
                    trid = track[u'trackId']
                    if plduptracks.has_key(trid):
                        plduptracks[trid].append(track[u'id'])
                    else:
                        plduptracks[trid] = [track[u'id']]

    def sanity_check(self):
        """Examine the data to confirm or expose mistaken assumptions."""

        # All playlists are of kind u'sj#playlist':
        print "Confirming expected user playlists types..."
        self.get_playlists()
        for pl in self._plcontents:
            assert pl[u'kind'] == u'sj#playlist'

        # Every track id in plists_dups is a key in self._songs_by_id:
        print "Confirming all playlist tracks are valid song ids..."
        self.get_songs()
        for apl_dups in self._pllsts_dups.values():
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
    def dump_stash(self, data):
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
    print
    return got
