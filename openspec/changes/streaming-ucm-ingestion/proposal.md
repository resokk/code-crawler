# Streaming UCM ingestion

COPY is chunked, but the loader needs the complete UcmBatch in memory. Add a
streaming input contract that loads typed facts chunk by chunk through staging,
supports forward references and keeps the load atomic. The batch loader stays and
the indexer is not switched in this change.
