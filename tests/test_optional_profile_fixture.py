from types import SimpleNamespace
from scripts.profile_library import restricted_summary_route


class Database:
    def __init__(self, episode, summary):
        self.rows={'episode_source_access':episode, 'summaries':summary}
        # Use actual persisted columns from the source-access migration, not
        # the enriched EpisodeRecord fields returned by application adapters.
        self.columns={'episode_source_access':{'user_id','eid','status'},
                      'summaries':{'user_id','episode_id'}}
        self.calls=[]
    def table(self, table):
        self.table_name=table
        self.calls.append((table,[]))
        return self
    def select(self, fields):
        assert set(fields.split(',')) <= self.columns[self.table_name]
        return self
    def eq(self, *args):
        assert args[0] in self.columns[self.table_name]
        self.calls[-1][1].append(args)
        return self
    def limit(self, *args): return self
    def execute(self): return SimpleNamespace(data=self.rows[self.table_name])


def test_deleted_preview_summary_is_not_reported_as_a_broken_current_route():
    db=Database([{'eid':'fixture'}],[])
    assert restricted_summary_route(db,'owner') is None
    assert ('user_id','owner') in db.calls[0][1] and ('user_id','owner') in db.calls[1][1]
    assert db.calls[0][0]=='episode_source_access'
    assert ('status','purchase_required') in db.calls[0][1]


def test_existing_restricted_note_is_still_checked():
    assert restricted_summary_route(Database([{'eid':'fixture'}],[{'episode_id':'fixture'}]),'owner') == '/api/summaries/6ad08b370e4e410a05bd4fd0'
    db=Database([],[])
    assert restricted_summary_route(db,'owner') is None and len(db.calls)==1
