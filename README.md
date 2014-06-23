PlaylistUtils
=============

Miscellaneous music playlist utilities

* **GoogleMusic**
  * ***PlaylistsCuller*** - Remove duplicate playlist items.

    This script is a work in progress, near by not quite operational. I will
    update when it's ready.

    I use iTunes playlists to organize music to make it easy to hear a
    particular kind of thing when I wish. Over time I've accumulated very
    many and sizable playlists.  I use Google Music Manager to sync my
    iTunes playlists to Google Music, and there's a serious problem. It
    perpetually duplicates items in my playlists, to the point where the
    Google Music versions of all my lists are 8 to 10 times the size of my
    original iTunes lists.

    This slows down my Google music clients drastically, and ruins
    sequencing in shuffle play, with so many duplicates to cull. It's
    untenable (and extremely aggravating) to even consider culling the many
    thousands of duplicates by hand!

    Fortunately, there is the [Unofficial Google Music
    API](https://github.com/simon-weber/Unofficial-Google-Music-API), an
    independently crafted Python interface to the unpublished Google Music
    api, by which the duplicates can be automatically culled. That's what
    this script is for.
