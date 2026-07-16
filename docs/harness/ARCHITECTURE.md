# Architecture

```text
FIFA goal involvements
  -> match_flow goal records with scorer, assister, and state tags
  -> player_flow_impacts
       scorer raw tags + one max context value per goal
       assister raw tags + scaled max context value per assisted goal
  -> editorial_scoring v0.5
       whole-match headline/composite surface
       decisive-moment impact role surface
  -> candidate_pool
  -> selector_input
  -> selection_review_payload with Player of the Day challengers
  -> bounded selection and copy loops
```

The existing public award types remain unchanged. The scoring version and active experiment are registry-controlled so rollback does not require code reversal.
