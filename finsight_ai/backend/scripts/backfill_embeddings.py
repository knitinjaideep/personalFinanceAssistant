"""
One-time backfill: generate embeddings for documents whose chunks were created
while embedding generation was accidentally disabled (commit 7aaa39e removed
the _generate_embeddings call from ingestion.py / reprocess_service.py; it has
since been restored).

Usage: python scripts/backfill_embeddings.py
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import text

from app.db.engine import get_session
from app.services.ingestion import _generate_embeddings


async def main() -> None:
    async with get_session() as session:
        rows = (await session.execute(
            text("SELECT DISTINCT document_id FROM text_chunks WHERE embedding IS NULL")
        )).fetchall()
        doc_ids = [r[0] for r in rows]

    print(f"Found {len(doc_ids)} document(s) with missing embeddings.")
    for doc_id in doc_ids:
        count = await _generate_embeddings(doc_id)
        print(f"  {doc_id}: embedded {count} chunk(s)")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
