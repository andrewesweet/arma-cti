### Changed

- `REVIEW_DELIVERY_PROTOCOL` now states the surface its duplication rule inspects: a marker
  counts only as an exact whole line of the captured stdout, a styled, prefixed or indented
  rendering is ordinary text, and the pair must appear exactly once across everything the
  reviewer prints. Delivery behaviour is unchanged — duplicated exact markers, reversed
  markers and an empty bounded section already refused with `review_delivery_failed` — and
  the #584 observation of three marker pairs passing came from the dispatch log, which
  interleaves child stderr with the dispatcher's echo of captured stdout, not from the
  captured stream the extraction judges. New tests pin the filed triple-pair shape and the
  bare empty pair as refusals, and pin that inexact renderings beside one exact pair still
  deliver exactly that pair's section (#584).
