"""One failed attempt should have one outstanding retry, including concurrent clicks."""
import asyncio
import pytest
from api.schemas import ProcessingStatus


@pytest.mark.asyncio
async def test_concurrent_retries_share_one_durable_job_and_worker(client):
 from api.routers import processing
 processing.jobs['retry-parent']=ProcessingStatus(job_id='retry-parent',user_id='local',status='failed',source_url='apple://saved-episode',episode_id='saved-episode',resummarize=True,llm_model='selected-model')
 first,second=await asyncio.gather(client.post('/api/jobs/retry-parent/retry'),client.post('/api/jobs/retry-parent/retry'))
 assert first.status_code==second.status_code==200
 assert first.json()['new_job_id']==second.json()['new_job_id']
 assert len(processing.jobs)==2
 assert processing.process_episode_async.await_count==1
 job=processing.jobs[first.json()['new_job_id']]
 assert job.resummarize and job.llm_model=='selected-model'


@pytest.mark.asyncio
@pytest.mark.parametrize('status',['completed','failed','cancelled','cancelling'])
async def test_finished_or_stopping_retry_does_not_prevent_a_new_attempt(client,status):
 from api.routers import processing
 processing.jobs['retry-parent']=ProcessingStatus(job_id='retry-parent',user_id='local',status='failed',source_url='apple://saved-episode')
 first=await client.post('/api/jobs/retry-parent/retry')
 old=first.json()['new_job_id'];processing.jobs[old].status=status
 second=await client.post('/api/jobs/retry-parent/retry')
 assert second.status_code==200 and second.json()['new_job_id']!=old
 assert processing.process_episode_async.await_count==2


@pytest.mark.asyncio
async def test_failed_durable_admission_is_not_reused_as_a_queued_retry(client,monkeypatch):
 from api.routers import processing
 from unittest.mock import Mock
 save=Mock(side_effect=[RuntimeError('History unavailable'),None])
 monkeypatch.setattr('api.job_persistence.save_job',save)
 processing.jobs['retry-parent']=ProcessingStatus(job_id='retry-parent',user_id='local',status='failed',source_url='apple://saved-episode')
 first=await client.post('/api/jobs/retry-parent/retry')
 assert first.status_code==503
 failed={job.job_id for job in processing.jobs.values() if job.job_id!='retry-parent'}
 second=await client.post('/api/jobs/retry-parent/retry')
 assert second.status_code==200 and second.json()['new_job_id'] not in failed
 assert processing.process_episode_async.await_count==1


@pytest.mark.asyncio
async def test_unrelated_retries_are_not_blocked_by_slow_admission(client,monkeypatch):
 from api.routers import processing
 entered,release=asyncio.Event(),asyncio.Event()
 original=processing._persist_new_job
 async def persist(job):
  if job.source_url=='apple://slow':
   entered.set();await release.wait()
  await original(job)
 monkeypatch.setattr(processing,'_persist_new_job',persist)
 for name in ['slow','fast']:
  processing.jobs[name]=ProcessingStatus(job_id=name,user_id='local',status='failed',source_url='apple://'+name)
 pending=asyncio.create_task(client.post('/api/jobs/slow/retry'))
 try:
  await asyncio.wait_for(entered.wait(),1)
  other=await asyncio.wait_for(client.post('/api/jobs/fast/retry'),1)
  assert other.status_code==200
 finally:
  release.set();await pending


@pytest.mark.asyncio
async def test_retry_reuse_does_not_expose_another_owners_task(client):
 from api.routers import processing
 processing.jobs['retry-parent']=ProcessingStatus(job_id='retry-parent',user_id='local',status='failed',source_url='apple://saved-episode')
 first=await client.post('/api/jobs/retry-parent/retry')
 processing.jobs['retry-parent'].user_id='different-owner'
 forbidden=await client.post('/api/jobs/retry-parent/retry')
 assert first.status_code==200 and forbidden.status_code==404
 assert processing.process_episode_async.await_count==1
