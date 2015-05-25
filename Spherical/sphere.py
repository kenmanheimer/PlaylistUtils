"""A container with elements that can reside in multiple locations.

The contained elements are, themselves, spheres, and a sphere can have 
different contents in different locations.

See the Sphere class description for details.
"""

class Sphere(Item):
    """A container of Spheres, which elements can reside in multiple locations.

    The contained elements:

    * Can have different contents in their different locations. I.e. their
      content is context-specific.
    * Contains the consolidation of their distinct instances, in contexts
      which encompass distinct instances.
    """
    # In the initial implementation, different variants of a sphere will be
    # distinct objects that know how to present consolidated versions of
    # contained spheres with multiple distinct instances.
