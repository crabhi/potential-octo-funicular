module generated_trace_stale {
  import cms(CHECK_AT_ACTION = true).* from "../model/cms"

  run traceReplayTest = init
    .then(loginU(2))
    .then(loginU(1))
    .then(submitReviewU(1, 1))
    .then(adminDemote)  // target (from log, informational only): {'user': 2}
    .then(publishU(2, 1))
    .expect(lastActionOk)
}
