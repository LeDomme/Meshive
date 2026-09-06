"""Reproducible P5 benchmark; deliberately imports the production evaluator."""
import json
import tracemalloc
from time import perf_counter

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from meshive.database import Base
from meshive.models.catalog import Archive, ArchiveEntry, LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.tag import (
    ModelTag,
    Tag,
    TagAssignmentRule,
    TagAssignmentRuleMatch,
    TagAssignmentRuleTarget,
)
from meshive.services.tag_assignment_rules import reevaluate_canonical_rules

MODELS = 4_000
ENTRIES_PER_ARCHIVE = 24


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    statements = 0
    @event.listens_for(engine, "before_cursor_execute")
    def count_statements(*_args: object) -> None:
        nonlocal statements
        statements += 1
    with Session(engine) as session:
        sources = [LibrarySource(name=f"Source {index}", root_path=f"/benchmark/{index}", directory_pattern="{model}") for index in range(2)]
        session.add_all(sources); session.flush()
        for index in range(MODELS):
            model = LibraryModel(library_source_id=sources[index % 2].id, relative_path=f"Creator {index % 80}/Series {index % 20}/Model {index:04}", name=f"Model {index:04}", status="available")
            session.add(model); session.flush()
            archive = Archive(model_id=model.id, filename=f"Model {index:04}.7z", relative_path=f"Model {index:04}.7z", format="7z", size_bytes=1, modified_ns=1, status="ready", entry_count=ENTRIES_PER_ARCHIVE)
            session.add(archive); session.flush()
            session.add_all(ArchiveEntry(archive_id=archive.id, path=f"STL/part-{entry:02}.stl", name=f"part-{entry:02}.stl", is_directory=False, size_bytes=1) for entry in range(ENTRIES_PER_ARCHIVE))
        session.flush()
        tags = [Tag(name=f"Benchmark {index}") for index in range(4)]
        session.add_all(tags); session.flush()
        rules = [
            TagAssignmentRule(tag_id=tags[0].id, match_mode="contains", pattern="part-12", enabled=True),
            TagAssignmentRule(tag_id=tags[1].id, library_source_id=sources[0].id, match_mode="regex", pattern=r"part-(0[0-9]|1[0-9])", enabled=True),
            TagAssignmentRule(tag_id=tags[2].id, match_mode="path_relation", path_value="Creator 1", path_relation="self_or_descendant", enabled=True),
            TagAssignmentRule(tag_id=tags[3].id, library_source_id=sources[1].id, match_mode="contains", pattern="Model", enabled=True),
        ]
        session.add_all(rules); session.flush()
        session.add_all([
            TagAssignmentRuleTarget(tag_assignment_rule_id=rules[0].id, target_type="archive_entry_name"),
            TagAssignmentRuleTarget(tag_assignment_rule_id=rules[1].id, target_type="archive_entry_path"),
            TagAssignmentRuleTarget(tag_assignment_rule_id=rules[2].id, target_type="model_relative_path"),
            TagAssignmentRuleTarget(tag_assignment_rule_id=rules[3].id, target_type="archive_filename"),
        ])
        session.commit()
        tracemalloc.start(); started = perf_counter(); result = reevaluate_canonical_rules(session); session.commit(); elapsed = perf_counter() - started
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        print(json.dumps({"models": MODELS, "entries_per_archive": ENTRIES_PER_ARCHIVE, "wall_seconds": round(elapsed, 3), "sql_statements": statements, "peak_python_bytes": peak, "evaluator_result": result, "match_rows": session.scalar(select(func.count(TagAssignmentRuleMatch.id))), "assignment_model_tags": session.scalar(select(func.count(ModelTag.id)).where(ModelTag.is_assignment_rule.is_(True)))}, indent=2))


if __name__ == "__main__":
    main()
