"""
Mock Supabase client for testing.
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MockQueryResult:
    """Mock Supabase query result."""
    data: List[Dict[str, Any]] = field(default_factory=list)
    count: Optional[int] = None
    error: Optional[str] = None


class MockSupabaseTable:
    """Mock Supabase table operations."""
    
    def __init__(self, table_name: str, storage: Dict[str, List[Dict[str, Any]]]):
        self.table_name = table_name
        self.storage = storage
        self._filters = []
        self._select_fields = "*"
        self._order_field = None
        self._order_desc = False
        self._limit = None
        self._count_mode = None
        
        # Ensure table exists in storage
        if table_name not in self.storage:
            self.storage[table_name] = []
    
    def select(self, fields: str = "*", count: str = None) -> "MockSupabaseTable":
        """Select fields."""
        self._select_fields = fields
        self._count_mode = count
        return self
    
    def eq(self, field: str, value: Any) -> "MockSupabaseTable":
        """Equal filter."""
        self._filters.append(("eq", field, value))
        return self
    
    def in_(self, field: str, values: List[Any]) -> "MockSupabaseTable":
        """In filter."""
        self._filters.append(("in", field, values))
        return self
    
    def order(self, field: str, desc: bool = False) -> "MockSupabaseTable":
        """Order results."""
        self._order_field = field
        self._order_desc = desc
        return self
    
    def limit(self, count: int) -> "MockSupabaseTable":
        """Limit results."""
        self._limit = count
        return self
    
    def execute(self) -> MockQueryResult:
        """Execute query."""
        data = self.storage.get(self.table_name, [])
        
        # Apply filters
        for filter_type, field, value in self._filters:
            if filter_type == "eq":
                data = [r for r in data if r.get(field) == value]
            elif filter_type == "in":
                data = [r for r in data if r.get(field) in value]
        
        # Apply ordering
        if self._order_field:
            data = sorted(data, key=lambda x: x.get(self._order_field, ""), reverse=self._order_desc)
        
        # Apply limit
        if self._limit:
            data = data[:self._limit]
        
        # Reset state
        self._filters = []
        self._select_fields = "*"
        self._order_field = None
        self._order_desc = False
        self._limit = None
        
        count = len(data) if self._count_mode else None
        self._count_mode = None
        
        return MockQueryResult(data=data, count=count)
    
    def insert(self, data: Dict[str, Any]) -> "MockSupabaseTable":
        """Insert data."""
        self._insert_data = data
        return self
    
    def upsert(self, data: Dict[str, Any]) -> "MockSupabaseTable":
        """Upsert data."""
        self._upsert_data = data
        return self
    
    def update(self, data: Dict[str, Any]) -> "MockSupabaseTable":
        """Update data."""
        self._update_data = data
        return self
    
    def delete(self) -> "MockSupabaseTable":
        """Delete data."""
        self._delete = True
        return self


class MockSupabaseClient:
    """Mock Supabase client for testing."""
    
    def __init__(self):
        self.storage: Dict[str, List[Dict[str, Any]]] = {
            "podcasts": [],
            "episodes": [],
            "transcripts": [],
            "transcript_segments": [],
            "summaries": [],
            "summary_key_points": [],
        }
        self._auto_id = 1
    
    def table(self, name: str) -> MockSupabaseTable:
        """Get table reference."""
        return MockSupabaseTable(name, self.storage)
    
    def add_podcast(self, user_id: str, pid: str, title: str, **kwargs) -> Dict[str, Any]:
        """Helper to add a podcast."""
        record = {
            "id": self._auto_id,
            "user_id": user_id,
            "pid": pid,
            "title": title,
            "author": kwargs.get("author", ""),
            "description": kwargs.get("description", ""),
            "cover_url": kwargs.get("cover_url", ""),
            "created_at": datetime.now().isoformat(),
        }
        self._auto_id += 1
        self.storage["podcasts"].append(record)
        return record
    
    def add_episode(self, user_id: str, eid: str, pid: str, **kwargs) -> Dict[str, Any]:
        """Helper to add an episode."""
        record = {
            "id": self._auto_id,
            "user_id": user_id,
            "eid": eid,
            "pid": pid,
            "title": kwargs.get("title", ""),
            "description": kwargs.get("description", ""),
            "duration": kwargs.get("duration", 0),
            "pub_date": kwargs.get("pub_date", ""),
            "audio_url": kwargs.get("audio_url", ""),
            "status": kwargs.get("status", "pending"),
            "created_at": datetime.now().isoformat(),
        }
        self._auto_id += 1
        self.storage["episodes"].append(record)
        return record
    
    def clear_all(self):
        """Clear all data."""
        for table in self.storage:
            self.storage[table] = []
        self._auto_id = 1
    
    def get_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """Get all data from a table."""
        return self.storage.get(table_name, [])
