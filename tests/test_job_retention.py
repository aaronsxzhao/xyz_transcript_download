"""History retention is chronological and never removes queued or running work."""
from api.schemas import ProcessingStatus
import time
import pytest


def test_retention_uses_known_time_instead_of_random_uuid_order(monkeypatch):
 from api.routers import processing
 monkeypatch.setattr(processing,'jobs',{
  'zz-old':ProcessingStatus(job_id='zz-old',status='completed',started_at=100),
  'aa-new':ProcessingStatus(job_id='aa-new',status='failed',started_at=200),
  'queued':ProcessingStatus(job_id='queued',status='pending'),
  'stopping':ProcessingStatus(job_id='stopping',status='cancelling'),
 })
 monkeypatch.setattr(processing,'_save_jobs_to_file_unlocked',lambda:None)
 processing._cleanup_old_jobs(max_completed_jobs=1)
 assert set(processing.jobs)=={'aa-new','queued','stopping'}


def test_admission_failures_without_a_worker_start_are_retained_by_creation_time(monkeypatch):
 from api.routers import processing
 monkeypatch.setattr(processing,'jobs',{
  'old':ProcessingStatus(job_id='old',status='completed',started_at=100),
  'new':ProcessingStatus(job_id='new',status='failed',created_at=200),
 })
 monkeypatch.setattr(processing,'_save_jobs_to_file_unlocked',lambda:None)
 processing._cleanup_old_jobs(max_completed_jobs=1)
 assert set(processing.jobs)=={'new'}


@pytest.mark.asyncio
async def test_admission_records_creation_time_without_waiting_for_worker_start(client):
 from api.routers import processing
 before=time.time()
 response=await client.post('/api/process',json={'episode_url':'apple://saved-episode'})
 assert response.status_code==200
 job=processing.jobs[response.json()['job_id']]
 assert before<=job.created_at<=time.time()
 assert job.started_at==0
