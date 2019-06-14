#!/usr/bin/env python

"""Remove duplicate song entries in all your GMusic playlists.

We require on gmusicapi being installed in the python running the script:

    https://github.com/simon-weber/Unofficial-Google-Music-API

## Authentication

The script will establish Google account OAuth credentials for you, using a
device you select from among your Google Play Music devices. The device ID is
stashed in in the script directory in a file named `.device_id`. The OAuth
authentication credentials are stashed by the gmusicapi in your homedir. The
location is specific to platform type.

## Operational Nuances

The script is designed to be usable for incremental progress - a new run will
not have to repeat the work of prior runs, and in fact you can interrupt it at
whim and then resume with a new run.

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
'~/.playlistsculler.json' (to change see STASH_PATH).

During operation you might see warnings with InsecurePlatformWarning and
InsecureRequestWarning mentioned. Answers to this stackoverflow question
mitigate them:

https://stackoverflow.com/questions/29134512/insecureplatformwarning-a-true-sslcontext-object-is-not-available-this-prevent

2019-06-14: Automate OAuth setup, with user input.
2019-04-25: Upgrade to recent gmusicapi, and implement basic oauth with even
            more basic instructions.
2018-12-27: Operation under Python 3 appears to be much faster.
"""

from gmusicapi import Mobileclient, exceptions
import json
import sys
import os
import stat
import pprint
from os import path
from datetime import datetime, timedelta


STASH_PATH = "~/.playlistsculler.json"
# Batch removal requests to this:
DEFAULT_BATCH_SIZE = 100
# VERBOSE: say much of what's happening while it's happening.
VERBOSE = True
# DRY_RUN True means prospective playlist removals are only reported, not done.
DRY_RUN = False

# DEVICE_ID_FILE_NAME is situated in the script directory.
DEVICE_ID_FILE_NAME = ".device_id"


class PlaylistsCuller:
    """Cull duplicate track entries from Google Music account's playlists."""

    _api = None                 # The GMusic API instance
    _playlists = None           # _api.get_all_user_playlist_contents() result
    _plnames_by_id = None       # {playlistId: playlist_name}
    _pldups = None              # {playlistId: {songId: [plEntryId, ...]}}
    # optional _songs_by_id, only for sanity check:
    _songs_by_id = None         # {songId: songMetadata, ...}
    _chosen = {}                # {plId: {songId: trackId}}
    _history = None
    tallies = {}

    def __init__(self):
        self._api = Mobileclient(debug_logging=True,
                                 validate=True,
                                 verify_ssl=True)
        device_id = self.establish_device_id()
        if device_id is not None:
            if not os.path.exists(self.oauth_filepath()):
                device_id = self.establish_device_id()
            self._api.oauth_login(device_id)
        self._pldups = {}

    def is_authenticated(self):
        return self._api.is_authenticated()

    def establish_oauth(self):
        sys.stderr.writelines(
            "\nFollow these instructions to do an OAuth login:\n")
        self._api.perform_oauth()

    def oauth_filepath(self):
        return self._api.OAUTH_FILEPATH

    def establish_device_id(self):
        """Get device ID according to stashed or new setting and do OAuth login.

        The established value is situated in the script directory with
        filename DEVICE_ID_FILE.

        When there is no established setting the user is presented with their
        current device IDs and offered the option to enter one to be stashed
        and used.
        """

        moddir = os.path.dirname(sys.modules[__name__].__file__)
        devid_file_path = os.path.join(moddir, DEVICE_ID_FILE_NAME)
        try:
            devid_file = open(devid_file_path, 'r')
            device_id = devid_file.read().strip()
            devid_file.close()
            return device_id
        except IOError:
            api = self._api
            try:
                api.oauth_login("tell me")
                if not api.is_authenticated():
                    self.establish_oauth()
                # oauth_login succeeded! We don't have the device id, but don't
                # need it this time.
                return
            except exceptions.NotLoggedIn:
                try:
                    api.oauth_login("tell me")
                except exceptions.InvalidDeviceId:
                    ids = sys.exc_info()[1].valid_device_ids
            except exceptions.InvalidDeviceId:
                ids = sys.exc_info()[1].valid_device_ids
            sys.stderr.writelines("Device ID unselected for this host...\n\n")
            if ids:
                sys.stderr.writelines("Here are your current devices: \n")
                for i in range(len(ids)):
                    print("%i: %s" % (i, ids[i]))
            sys.stderr.write("Choose the number of a device ID to use"
                             " (or anything else to cancel): ")
            sys.stderr.flush()
            choice = sys.stdin.readline().strip()
            try:
                device_id = ids[int(choice)]
            except ValueError:
                sys.stderr.writelines("Cancelled.\n\n")
                return None
            devid_file = open(devid_file_path, 'w')
            # Before adding device ID, restrict access to only the owner:
            os.chmod(devid_file_path, stat.S_IREAD | stat.S_IWRITE)
            devid_file.writelines(device_id + "\n")
            devid_file.close()
            sys.stderr.writelines("\nUsing device id: %s\n" % device_id)
            self.establish_oauth()
            return device_id

    def process(self):
        if DRY_RUN:
            print("DRY_RUN - playlist removals inhibited")
        # Get playlists, depending on freshness check for economy:
        self.get_playlists()
        self.fetch_stash()
        self.arrange_playlists_contents()
        self.do_tally('pre')
        blather("Pre-cull:")
        blather(pprint.pformat(self.tallies['pre']))
        if self.tallies['pre']['dups'] == 0:
            blather("No dups, nothing to do.")
        else:
            try:
                self.do_cull()
            finally:
                # Re-fetch the playlists from the server, if any are modified:
                self.get_playlists(refresh=True)
                self.arrange_playlists_contents()
                # Preserve and present reflect incremental progress, whether
                # or not we completed:
                self.do_tally('post')
                blather("Post-cull:")
                blather(pprint.pformat(self.tallies['post']))
                if not DRY_RUN:
                    self.store_stash()

    def do_cull(self):
        """Remove playlist's duplicate tracks.

        To reduce churn, we try to be clever about which track we keep.
        1. We prefer a choice we've seen before, supposing that it's stable.
        2. But if we have only the choice and one other item, try the other,
           in case it's better.
        It's likely there is a right choice, but worth probing for it."""

        before = datetime.now()
        doingpl = doingsong = 0
        removed = 0
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
                            # Try new alternative - prior didn't last.
                            choice, entries = entries[0], [choice]
                    else:
                        choice = entries.pop(0)
                    # Remove remaining entries:
                    removed += len(entries)
                    batcher.batch_entries(entries)
                    # Revise our records assuming the removals succeeded:
                    # XXX self._pldups[plId][songId] = [choice]
                elif entries:
                    choice = entries[0]
                if choice:
                    # Register choice whether or not any removals happened -
                    # duplicates may be present next time we run, and we
                    # specifically want to prefer oldest/most stable one.
                    self.register_chosen(plId, songId, choice)
            batcher.finish_batch()
        blather("%d tracks removed, from %d lists of %d total (%s elapsed)."
                % (removed, batcher.num_lists_changed, doingpl,
                   elapsed_since_rounded(before)))

    def get_chosen(self, plId, songId):
        "Return preferred track for playlist plId and song songId, or None."
        if (plId in self._chosen
                and songId in self._chosen[plId]):
            return self._chosen[plId][songId]
        else:
            return None

    def register_chosen(self, plId, songId, trackId):
        """Register trackId as choice for playlist plId and song songId."""
        if plId in self._chosen:
            self._chosen[plId][songId] = trackId
        else:
            self._chosen[plId] = {songId: trackId}

    def fetch_stash(self):
        fetched = Stasher(STASH_PATH).fetch_stash() or {'chosen': {},
                                                        'history': []}
        self._history = fetched['history']
        self._chosen = fetched['chosen']

    def store_stash(self):
        self._history.insert(0, (str(datetime.now()), self.tallies))
        Stasher(STASH_PATH).store_stash({'chosen': self._chosen,
                                         'history': self._history})

    def get_playlists(self, refresh=False):
        """Populate self._playlists, including tracks.

        We avoid unnecessary call to API's exhaustive
        .get_all_user_playlist_contents()' by checking '.get_all_playlists()'
        to compare lastModifiedTimestamp against previous fetch, if any."""
        # We already know a full fetch is needed if we have no prior:
        needed = not self._playlists or refresh
        if not needed:
            # Compare timestamps against brief (sans tracks) current report.
            blather("Fetching compact data to compare timestamps... ",
                    True)
            compact = incr_getter(
                self._api.get_all_playlists(incremental=True))
            blather("...")
            lastmods = {x['id']: x['lastModifiedTimestamp'] for x in compact}
            if len(lastmods) != len(self._playlists):
                needed = True
            else:
                for pl in self._playlists:
                    if (not pl['id'] in lastmods
                        or (pl['lastModifiedTimestamp'] !=
                            lastmods[pl['id']])):
                        needed = True
                        break
            if needed:
                blather("Discrepancies found,"
                        " proceeding with exhaustive fetch.")
        if needed:
            before = datetime.now()
            blather("...getting playlists... ")
            self._playlists = self._api.get_all_user_playlist_contents()
            blather("... Done (%s elapsed)." % elapsed_since_rounded(before))
        else:
            blather("Previously fetched data is already up-to-date.")

    def get_songs(self):
        """Get all songs in self._songs_by_id

        This is optional, just for sanity check."""
        if (not self._songs_by_id):
            blather("Getting songs...")
            songs = incr_getter(self._api.get_all_songs(incremental=False))
            self._songs_by_id = {song[u'id']: song for song in songs}
            blather(" Done.")

    def arrange_playlists_contents(self):
        self._plnames_by_id = {}
        self._pldups = {}
        for pl in self._playlists:
            plId = pl[u'id']
            trackdups = self._pldups[plId] = {}
            self._plnames_by_id[plId] = pl[u'name']
            for track in pl[u'tracks']:
                trId = track[u'trackId']
                if trId in trackdups:
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
                assert trId in self._songs_by_id


class BatchedRemover:
    """Batch playlist entry removal requests to reduce transactions."""
    def __init__(self, api, plnum, plname, batch_size=DEFAULT_BATCH_SIZE):
        self.emitted = False
        self.api = api
        self.plname = plname
        self.plnum = plnum
        self.batch_size = batch_size
        self.entries = []
        self.num_removals = 0
        self.num_fails = 0
        self._num_lists_changed = 0

    @property
    def num_lists_changed(self):
        "Return the number of lists that have been changed so far."
        return self._num_lists_changed

    def batch_entries(self, entries):
        if not self.emitted:
            blather("Playlist #%d: %s" % (self.plnum, self.plname))
            self._num_lists_changed += 1
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
        if self.num_removals and self.num_removals > self.batch_size:
            message = format(" %d" % self.num_removals)
            if self.num_fails:
                message += format(", %d fails" % self.num_fails)
            blather(message)

    def do_removals(self, entries):
        if entries:
            eqls = "= %d" % len(entries)
            if self.entries:
                eqls += " + %d" % len(self.entries)
            self.num_removals += len(entries)
            if DRY_RUN:
                blather("would" + eqls)
            else:
                removed = self.api.remove_entries_from_playlist(entries)
                if len(removed) != len(entries):
                    diff = len(entries) - len(removed)
                    self.num_fails += diff
                    self.api.logger.warning("Playlist %s: %d removals failed"
                                            % (self.plname, diff))
                    blather("%s - %d missed" % (eqls, len(entries), diff))
                else:
                    blather(eqls)
            if self.entries:
                blather("%d " % len(self.entries), nonewline=True)


class Stasher:
    """Provide JSON externalization of a data structure to a location."""
    _stash_path = None

    def __init__(self, stash_path):
        """Stash location can include '~' and var references.

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


def elapsed_since_rounded(dt):
    """Return rough datetime delta since datetime DT."""
    elapsed = datetime.now() - dt
    return timedelta(seconds=round(elapsed.seconds, 0))


def blather(msg, nonewline=False):
    "Print message if in verbose mode."
    if VERBOSE:
        if nonewline:
            sys.stdout.write(msg)
            sys.stdout.flush()
        else:
            print(msg)


def migrate_version(culler, password):
    """Return a new culler, from the reloaded module, with culler's data.

    WON'T WORK when running this module as a script."""
    try:
        from imp import reload
    except ImportError:
        from importlib import reload
    reload(sys.modules[__name__])
    newculler = PlaylistsCuller()
    for field in ['_playlists', '_pldups', '_songs_by_id',
                  '_chosen', '_history']:
        setattr(newculler, field, getattr(culler, field))
    return newculler


if __name__ == "__main__":
    plc = PlaylistsCuller()
    if plc.is_authenticated():
        plc.process()
