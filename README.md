PlaylistUtils
=============

Miscellaneous music playlist utilities

* **GoogleMusic**
  * ***PlaylistsCuller.py*** - Remove duplicate playlist items.

    Remove Google Music playlist duplicate items.

    This script is a work in progress, near but not quite operational. I'm
    going to update when it's ready.

    I use Google Music Manager to sync my iTunes playlists to Google Music,
    and have always experienced an odd and serious problem with it. Almost
    any time I add new, non-duplicate items to my iTunes playlists, seeming
    random, already existing items on the playlists are duplicated. After a
    while, not realizing this was happening, I had accumulated lists that
    were bulked with duplicates to 10 to 20 times their actual size. So my
    hundred and fifty or two hundred playlists, which amounted to ten or
    twenty thousand distinct entries, were mostly duplicates totalling
    hundreds of thousands of items!

    The massive duplicates made the android versions of playlists
    unusable. Even if the devices could handle the extra load, the UI is
    horrible for navigating even small playlists, and totally useless for
    finding items I wanted to listen to among the tens of thousands of
    duplicates! Culling the duplicates by hand was not tenable.

    Fortunately, there is the
    [Unofficial Google Music API](https://github.com/simon-weber/Unofficial-Google-Music-API),
    an independently crafted Python interface to the unpublished Google
    Music api, which I could use to craft a program to do the duplicates
    removal.

    That's what GoogleMusic/PlaylistCuller.py is for.

    The script is a work in progress. It works, and it tries to be
    efficient, reporting what it's doing along the way. It also continues
    to be necessary, because the random-duplication problems continue to
    this day.
