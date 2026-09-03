# Fixed

The provider-error breaker counts consecutive errors again, with no time bound: three
provider errors hold a lane whatever the interval between them, and the streak is cleared
only by a classified outcome of another kind. The 60-second pruning window that #420's
landing introduced silently overrode ADR-0066 Decision 3 and left a lane erroring every
couple of minutes reading as healthy.
