### Changed

- Controller reconciliation now observes typed, exact-candidate delivery evidence, retires
  completed Work Runs, and exposes newly unblocked Work Items. A cycle whose `planned`
  journal holds a Work Run launch now refuses on resume (`controller_resume_indeterminate`)
  rather than re-attempting the launch, because the journal cannot tell whether the
  interrupted apply ran; such a cycle stops the controller until it is resolved by hand
  (#631 carries that resolution work).
