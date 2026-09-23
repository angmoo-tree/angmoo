# SNS V2 verification artifacts

These files distinguish synthetic provider comparisons from read-only observations
of the local contributor environment. They contain no API keys, raw conversations,
memory bodies, or World Packages.

The activity, character, and memory identifiers in the public JSON reports are
deterministically pseudonymized. The private correspondence is not included in
the repository. Timestamps, statuses, counts, hashes, and duration measurements
remain the recorded results; an identifier in these reports is only useful for
joining rows within the published reports.

The provider comparison JSONL files use synthetic cases. Their model decisions
show the output of those bounded tests, not a claim that all natural activities
improve. The local pilot and recall files are read-only evidence and are not
replay inputs. See [the implementation structure](../../architecture/autonomous-activity-v2.md)
for the graph and its remaining user checks.
