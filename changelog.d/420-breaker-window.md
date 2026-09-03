# Fixed

- The lane breaker's provider-error rule now implements the window its comment stated:
  three provider errors within 60 seconds hold the lane, and errors older than the
  window fall out of the count instead of accumulating indefinitely (#420).
