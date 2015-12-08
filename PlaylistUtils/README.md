PlaylistUtils
=============

Miscellaneous music playlist utilities

* **GoogleMusic**
  * ***PlaylistsCuller.py*** - Remove duplicate playlist items.

    Remove Google Music playlist duplicate items.

    This script is a work in progress, near but not quite operational. I'm
    going to update when it's ready.

    I use Google Music Manager to sync my iTunes playlists to Google Music,
    and there's a serious problem with it. It perpetually duplicates items
    in my playlists, to the point where the Google Music versions of all my
    lists are 8 to 10 times the size of my original iTunes lists.

    This is a serious problem, because I have a lot of sizeable
    playlists. It's untenable (and extremely aggravating) to even consider
    culling the many thousands of duplicates by hand! But the massive
    bulking slows down my Google music clients drastically, and ruins
    sequencing in shuffle play, with so many duplicates to cull. This is
    only compounded by the terrible UI accommodation for large playlists in
    the design of the Google Play Music client.

    Fortunately, there is the [Unofficial Google Music
    API](https://github.com/simon-weber/Unofficial-Google-Music-API), an
    independently crafted Python interface to the unpublished Google Music
    api, by which the duplicates can be automatically culled. That's what
    this script is for.

    The script is a work in progress, near by not quite operational. I will
    update when it's doing the job.
