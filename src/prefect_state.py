from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from prefect.variables import Variable

ACTIVE_BATCHES_VAR = "active_batch_ids"
BATCH_RECORD_KEYS_VAR = "batch_record_keys"
FAILURE_COUNTS_VAR = "record_failure_counts"
INFLIGHT_RECORD_IDS_VAR = "inflight_record_ids"


class StateStore(Protocol):
    def get_active_batches(self) -> list[str]: ...

    def add_batch(self, batch_id: str, record_keys: list[str]) -> None: ...

    def remove_batch(self, batch_id: str) -> list[str]: ...

    def get_batch_record_keys(self, batch_id: str) -> list[str]: ...

    def get_failure_counts(self) -> dict[str, int]: ...

    def increment_failure_counts(self, failures: dict[str, str]) -> dict[str, int]: ...

    def get_inflight_records(self) -> set[str]: ...

    def add_inflight_records(self, record_keys: list[str]) -> None: ...

    def remove_inflight_records(self, record_keys: list[str]) -> None: ...


@dataclass
class PrefectVariableStateStore:
    active_batches_var: str = ACTIVE_BATCHES_VAR
    batch_record_keys_var: str = BATCH_RECORD_KEYS_VAR
    failure_counts_var: str = FAILURE_COUNTS_VAR
    inflight_records_var: str = INFLIGHT_RECORD_IDS_VAR

    def _get_list(self, var: str) -> list[str]:
        raw = Variable.get(var, default=[])
        if not isinstance(raw, list):
            return []
        return [str(x) for x in raw]

    def _get_dict(self, var: str) -> dict:
        raw = Variable.get(var, default={})
        if not isinstance(raw, dict):
            return {}
        return dict(raw)

    def get_active_batches(self) -> list[str]:
        return self._get_list(self.active_batches_var)

    def add_batch(self, batch_id: str, record_keys: list[str]) -> None:
        active = self.get_active_batches()
        if batch_id not in active:
            active.append(batch_id)
        Variable.set(self.active_batches_var, active, overwrite=True)

        mapping = self._get_dict(self.batch_record_keys_var)
        mapping[batch_id] = list(record_keys)
        Variable.set(self.batch_record_keys_var, mapping, overwrite=True)

        self.add_inflight_records(record_keys)

    def remove_batch(self, batch_id: str) -> list[str]:
        active = self.get_active_batches()
        if batch_id in active:
            active.remove(batch_id)
            Variable.set(self.active_batches_var, active, overwrite=True)

        mapping = self._get_dict(self.batch_record_keys_var)
        record_keys = mapping.pop(batch_id, [])
        Variable.set(self.batch_record_keys_var, mapping, overwrite=True)

        if record_keys:
            self.remove_inflight_records(record_keys)

        return [str(k) for k in record_keys]

    def get_batch_record_keys(self, batch_id: str) -> list[str]:
        mapping = self._get_dict(self.batch_record_keys_var)
        keys = mapping.get(batch_id, [])
        return [str(k) for k in keys]

    def get_failure_counts(self) -> dict[str, int]:
        raw = Variable.get(self.failure_counts_var, default={})
        if not isinstance(raw, dict):
            return {}
        counts: dict[str, int] = {}
        for key, value in raw.items():
            try:
                counts[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return counts

    def increment_failure_counts(self, failures: dict[str, str]) -> dict[str, int]:
        counts = self.get_failure_counts()
        for key in failures:
            counts[key] = counts.get(key, 0) + 1
        Variable.set(self.failure_counts_var, counts, overwrite=True)
        return counts

    def get_inflight_records(self) -> set[str]:
        return set(self._get_list(self.inflight_records_var))

    def add_inflight_records(self, record_keys: list[str]) -> None:
        inflight = self.get_inflight_records()
        inflight.update(record_keys)
        Variable.set(self.inflight_records_var, list(inflight), overwrite=True)

    def remove_inflight_records(self, record_keys: list[str]) -> None:
        inflight = self.get_inflight_records()
        inflight.difference_update(record_keys)
        Variable.set(self.inflight_records_var, list(inflight), overwrite=True)


@dataclass
class InMemoryStateStore:
    active_batches: list[str] | None = None
    batch_record_keys: dict[str, list[str]] | None = None
    failure_counts: dict[str, int] | None = None
    inflight_records: set[str] | None = None

    def __post_init__(self) -> None:
        if self.active_batches is None:
            self.active_batches = []
        if self.batch_record_keys is None:
            self.batch_record_keys = {}
        if self.failure_counts is None:
            self.failure_counts = {}
        if self.inflight_records is None:
            self.inflight_records = set()

    def get_active_batches(self) -> list[str]:
        return list(self.active_batches or [])

    def add_batch(self, batch_id: str, record_keys: list[str]) -> None:
        assert self.active_batches is not None
        assert self.batch_record_keys is not None
        if batch_id not in self.active_batches:
            self.active_batches.append(batch_id)
        self.batch_record_keys[batch_id] = list(record_keys)
        self.add_inflight_records(record_keys)

    def remove_batch(self, batch_id: str) -> list[str]:
        assert self.active_batches is not None
        assert self.batch_record_keys is not None
        if batch_id in self.active_batches:
            self.active_batches.remove(batch_id)
        record_keys = self.batch_record_keys.pop(batch_id, [])
        self.remove_inflight_records(record_keys)
        return list(record_keys)

    def get_batch_record_keys(self, batch_id: str) -> list[str]:
        assert self.batch_record_keys is not None
        return list(self.batch_record_keys.get(batch_id, []))

    def get_failure_counts(self) -> dict[str, int]:
        assert self.failure_counts is not None
        return dict(self.failure_counts)

    def increment_failure_counts(self, failures: dict[str, str]) -> dict[str, int]:
        assert self.failure_counts is not None
        for key in failures:
            self.failure_counts[key] = self.failure_counts.get(key, 0) + 1
        return dict(self.failure_counts)

    def get_inflight_records(self) -> set[str]:
        assert self.inflight_records is not None
        return set(self.inflight_records)

    def add_inflight_records(self, record_keys: list[str]) -> None:
        assert self.inflight_records is not None
        self.inflight_records.update(record_keys)

    def remove_inflight_records(self, record_keys: list[str]) -> None:
        assert self.inflight_records is not None
        self.inflight_records.difference_update(record_keys)
