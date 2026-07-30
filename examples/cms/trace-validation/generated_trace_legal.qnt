module generated_trace_legal {
  import cms(CHECK_AT_ACTION = true).* from "../model/cms"

  run traceReplayTest = init
    .then(loginU(1))
    .then(submitReviewU(1, 1))
    .then(loginU(2))
    .then(publishU(2, 1))
    .expect(lastActionOk)
}
