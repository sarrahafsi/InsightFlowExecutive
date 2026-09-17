"""
Shared lock serializing the first import/load of heavy ML libraries
(transformers, torch) across all NLP modules.

`@lru_cache(maxsize=1)` alone does NOT make a lazy-loader thread-safe: two
threads can both see "not cached yet" and enter the function body at the same
time. With several background jobs now running concurrently (periodic Gmail
sync, NLP enrichment job, realtime sync loop, image processor), that race
happens routinely — two threads triggering `from transformers import ...`
for the first time simultaneously corrupts the partially-initialized module,
observed as "Failed to import transformers.generation.utils ... maximum
recursion depth exceeded" for every classifier at once.

One process-wide lock around each lazy-loader's body ensures only one thread
ever performs the actual import/model-load at a time; import is idempotent
(cheap once `sys.modules` is populated) so serializing it costs nothing once
warm.
"""
import threading

MODEL_LOAD_LOCK = threading.Lock()
