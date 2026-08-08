from uuid import uuid4

from todo_buddy.models import BuddyDocument, Phase, SyncMetadata, Task


def create_sample_document() -> BuddyDocument:
    return BuddyDocument(
        schema_version=1,
        title="BUILD A THOUGHTFUL DEMO",
        phases=[
            Phase(
                id=str(uuid4()),
                title="PHASE 1: DISCOVER",
                tasks=[
                    Task(id=str(uuid4()), title="Collect useful references"),
                    Task(id=str(uuid4()), title="Choose the smallest clear direction"),
                ],
                color="#5B78C7",
            ),
            Phase(
                id=str(uuid4()),
                title="PHASE 2: MAKE",
                tasks=[
                    Task(id=str(uuid4()), title="Build the first working pass"),
                    Task(id=str(uuid4()), title="Check the important details"),
                    Task(id=str(uuid4()), title="Share the finished result"),
                ],
                color="#D48335",
            ),
        ],
        sync=SyncMetadata(),
    )
