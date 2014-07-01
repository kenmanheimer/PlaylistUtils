"""Remove duplicate song entries in all your GMusic playlists.

We require on gmusicapi being installed in the python running the script:

    https://github.com/simon-weber/Unofficial-Google-Music-API

This script is designed to be usable for incremental progress - a new run will
not have to repeat the work of prior runs, and in fact you can interrupt it at
whim.

For efficiency, we gather removal requests within a playlist into batches -
default size 100. The batches do not extend across playlists.

We indicate progress as it happens by printing the name of the playlist
currently being culled, if culling is required, and then a progressively
printed line of numbers, each indicating the number of duplicates being
removing for each duplicated track on the playlist. These notifications try
to tersely indicate what's happening as it happens. To reduce the output,
change VERBOSE assignment to False.

To reduce churn, we try to be clever about which we keep among a bunch of
duplicates:

1. We prefer a choice we've seen before, in the hopes that it's stable.
2. But if we have only the choice and one duplicate, try the new duplicate,
   in case it's better.

This choice juggling is an experiment. There may not be any stable choices.

In order to track the previous chocies, we maintain a json stash file in
'~/.playlistsculler.json' (configurable - see STASH_PATH).

"""


STASH_PATH = "~/.playlistsculler.json"
# Batch removal requests to this:
DEFAULT_BATCH_SIZE = 100
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
            # Preserve and present reflect incremental progress, whether or not
            # we completed:
            self.do_tally('post')
            if not DRY_RUN:
                self.store_stash()
            self.do_report()

    def do_cull(self):
        """Remove playlist's duplicate tracks.

        To reduce churn, we try to be clever about which track we keep. 
        1. We prefer a choice we've seen before, in the hopes that it's stable.
        2. But if we have only the choice and one other item, try the other,
           in case it's better.
        It's likely there is a right choice, but worth probing for it."""

        doingpl = doingsong = 0
        playlists = self._playlists
        total = len(self._pldups)
        for plId, pldups in self._pldups.items():
            doingpl += 1
            plname = self._plnames_by_id[plId]
            batcher = BatchedRemover(self._api, doingpl, plname)
            doingsong = 0
            for songId, entries in pldups.items():
                doingsong += 1
                choice = self.get_chosen(plId, songId)
                if len(entries) > 1:
                    if choice and (choice in entries):
                        entries.remove(choice)
                        if len(entries) == 1:
                            # Make the new item the choice, instead - since
                            # the previous choice is apparently not better:
                            choice, entries = entries[0], [choice]
                    else:
                        choice = entries.pop(0)
                    # Remove remaining entries:
                    batcher.batch_entries(entries)
                    # Revise our records assuming the removals succeeded:
                    #XXX self._pldups[plId][songId] = [choice]
                elif entries:
                    choice = entries[0]
                if choice:
                    # Register choice whether or not any removals happened -
                    # duplicates may be present next time we run, and we
                    # specifically want to prefer oldest/most stable one.
                    self.register_chosen(plId, songId, choice)
            batcher.finish_batch()
        blather("%s playlists processed." % doingpl)

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

class BatchedRemover:
    """Batch playlist entry removal requests to reduce transactions."""
    def __init__(self, api, plnum, plname, batch_size=DEFAULT_BATCH_SIZE):
        self.emitted = False
        self.api = api
        self.plname = plname
        self.plnum = plnum
        self.batch_size = batch_size
        self.entries = []
    def batch_entries(self, entries):
        if not self.emitted:
            blather("Playlist #%d: %s" % (self.plnum, self.plname))
            self.emitted = True
        blather("%d " % len(entries), nonewline=True)
        pending = self.entries
        pending.extend(entries)
        if len(pending) >= self.batch_size:
            self.entries = pending[self.batch_size:]
            pending = pending[:self.batch_size]
            self.do_removals(pending)
        else:
            self.entries = pending
    def finish_batch(self):
        pendings, self.entries = self.entries, []
        self.do_removals(pendings)
    def do_removals(self, entries):
        if entries:
            eqls = "= %d" % len(entries)
            if self.entries:
                eqls += " + %d" % len(self.entries)
            if DRY_RUN:
                blather("would" + eqls)
            else:
                removed = self.api.remove_entries_from_playlist(entries)
                if len(removed) != len(entries):
                    diff = len(entries) - len(removed)
                    self.api.logger.warning("Playlist %s: %d removals failed"
                                            % (self.plname, diff))
                    blather("%s - %d missed" % (eqls, len(entries), diff))
                else:
                    blather(eqls)
            if self.entries:
                blather("%d " % len(self.entries), nonewline=True)

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
